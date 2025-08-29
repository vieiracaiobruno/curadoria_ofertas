#!/usr/bin/env python3
"""
Pipeline completo de curadoria de ofertas
- Com passo de login no Mercado Livre (cookies reutilizáveis)
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timedelta

from dotenv import load_dotenv

# Adiciona o diretório raiz do projeto ao sys.path (ajuste se necessário)
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# Ajuste estes imports conforme a sua estrutura de pastas
from backend.db.database import SessionLocal
from backend.models.models import Usuario, Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta, HistoricoPreco
from backend.modules.collector import Collector
from backend.modules.validator import Validator
from backend.modules.publisher import Publisher
from backend.modules.metrics_analyzer import MetricsAnalyzer

# -----------------------------------------------------------------------------
# Configuração de logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./logs/pipeline.log"),
        logging.StreamHandler()
    ]
)

# -----------------------------------------------------------------------------
# Utilitários de cookies/login ML
# -----------------------------------------------------------------------------
def _load_cookies_from_file(cookies_file: str):
    if not os.path.exists(cookies_file):
        return None, None
    try:
        with open(cookies_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        created = datetime.fromisoformat(data.get("created_at"))
        return created, data.get("cookies", [])
    except Exception:
        return None, None

def _save_cookies_to_file(selenium_cookies: list, cookies_file: str):
    payload = {
        "created_at": datetime.utcnow().isoformat(),
        "cookies": []
    }
    for c in selenium_cookies:
        payload["cookies"].append({
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".mercadolivre.com.br"),
            "path": c.get("path", "/"),
            "expiry": c.get("expiry"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        })
    os.makedirs(os.path.dirname(cookies_file) or ".", exist_ok=True)
    with open(cookies_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _add_cookies_to_requests_session(sess: requests.Session, cookies: list):
    for c in cookies:
        kwargs = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".mercadolivre.com.br"),
            "path": c.get("path", "/"),
        }
        if c.get("expiry") is not None:
            kwargs["expires"] = c.get("expiry")
        sess.cookies.set(**kwargs)

def _selenium_login_and_get_cookies(email: str, password: str, headless: bool = True) -> list:
    """
    Abre navegador, faz login no ML e retorna cookies (lista de dicts no formato selenium).
    Se houver 2FA/CAPTCHA, rode headless=False e conclua manualmente; os cookies serão capturados.
    """
    try:
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        import undetected_chromedriver as uc
    except Exception as e:
        raise RuntimeError(
            "Dependências para login não instaladas. Rode:\n"
            "  pip install selenium undetected-chromedriver webdriver-manager"
        ) from e

    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,1200")
    options.add_argument("--lang=pt-BR")

    driver = uc.Chrome(options=options)
    try:
        wait = WebDriverWait(driver, 30)
        #driver.get("https://www.mercadolivre.com.br/hub/identity-login")
        driver.get("https://www.mercadolivre.com/jms/mlb/lgz/login")

        # Digita e envia e-mail
        def type_email():
            candidates = [
                (By.ID, "user_id"),
                (By.NAME, "user_id"),
                (By.CSS_SELECTOR, "input[name='user_id']"),
                (By.CSS_SELECTOR, "input[type='email']"),
            ]
            email_input = None
            for by, sel in candidates:
                try:
                    email_input = wait.until(EC.presence_of_element_located((by, sel)))
                    break
                except Exception:
                    continue
            if not email_input:
                return False
            email_input.clear()
            email_input.send_keys(email)
            # botão "continuar"
            for by, sel in [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.ID, "login_user_form"),
            ]:
                try:
                    driver.find_element(by, sel).click()
                    return True
                except Exception:
                    continue
            return False

        # Digita e envia senha
        def type_password():
            candidates = [
                (By.ID, "password"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, "input[name='password']"),
                (By.CSS_SELECTOR, "input[type='password']"),
            ]
            pwd_input = None
            for by, sel in candidates:
                try:
                    pwd_input = WebDriverWait(driver, 20).until(EC.presence_of_element_located((by, sel)))
                    break
                except Exception:
                    continue
            if not pwd_input:
                return False
            pwd_input.clear()
            pwd_input.send_keys(password)
            # botão "entrar"
            for by, sel in [
                (By.ID, "action-complete"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
            ]:
                try:
                    driver.find_element(by, sel).click()
                    return True
                except Exception:
                    continue
            return False

        type_email()
        type_password()

        # Espera redirect básico
        driver.implicitly_wait(5)

        cookies = driver.get_cookies()
        if not cookies and not headless:
            logging.info("Aguardando login manual (2FA/CAPTCHA)… Você tem 90s.")
            import time as _t
            _t.sleep(90)
            cookies = driver.get_cookies()

        return cookies
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def ensure_ml_login():
    """
    Garante que exista uma sessão autenticada no Mercado Livre:
    - Reutiliza cookies se ainda válidos (por idade)
    - Caso contrário, roda login via Selenium e salva cookies
    - Se ML_EMAIL/ML_PASSWORD não estiverem definidos, apenas registra aviso
    """
    load_dotenv("config.env")

    email = os.getenv("ML_EMAIL", "").strip()
    password = os.getenv("ML_PASSWORD", "").strip()
    cookies_file = os.getenv("ML_COOKIES_FILE", "./ml_cookies.json")
    reuse_days = int(os.getenv("ML_LOGIN_REUSE_DAYS", "14"))
    headless = os.getenv("ML_SELENIUM_HEADLESS", "True").strip().lower() in ("1", "true", "yes")

    if not email or not password:
        logging.warning("ML_EMAIL/ML_PASSWORD não configurados; seguindo sem login.")
        return

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "close",
    })

    # Tenta reutilizar cookies
    created, cookies = _load_cookies_from_file(cookies_file)
    if cookies and created and (datetime.utcnow() - created) < timedelta(days=reuse_days):
        _add_cookies_to_requests_session(sess, cookies)
        try:
            r = sess.get("https://www.mercadolivre.com.br/", timeout=15)
            if r.status_code == 200 and any(x in r.text for x in ("Minha conta", "Minha Conta", "Sair")):
                logging.info("Cookies do Mercado Livre reutilizados com sucesso.")
                return
        except Exception:
            pass
        logging.info("Cookies existentes parecem inválidos; tentando novo login…")

    # Login via Selenium
    logging.info("Fazendo login no Mercado Livre via Selenium…")
    selenium_cookies = _selenium_login_and_get_cookies(email, password, headless=headless)
    if not selenium_cookies:
        logging.warning("Não foi possível obter cookies via Selenium. Verifique credenciais/2FA.")
        return
    _save_cookies_to_file(selenium_cookies, cookies_file)
    logging.info("Login realizado e cookies salvos.")

# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------
def run_pipeline():
    db = SessionLocal()
    try:
        logging.info("=== Iniciando Pipeline de Curadoria de Ofertas ===")

        # 0) Login ML (gera/valida cookies antes da coleta)
        ensure_ml_login()

        # 1) Coleta de dados
        logging.info("Iniciando coleta de ofertas…")
        collector = Collector(db)
        collector.run_collection()
        logging.info("Coleta de ofertas concluída.")

        # 2) Validação
        logging.info("Iniciando validação de ofertas…")
        validator = Validator(db)
        validator.run_validation()
        logging.info("Validação de ofertas concluída.")

        # 3) Publicação
        logging.info("Iniciando publicação de ofertas…")
        publisher = Publisher(db)
        publisher.run_publication()
        logging.info("Publicação de ofertas concluída.")

        # 4) Análise de Métricas (opcional)
        logging.info("Iniciando análise de métricas…")
        metrics_analyzer = MetricsAnalyzer(db)
        metrics_analyzer.analyze_metrics()
        logging.info("Análise de métricas concluída.")

        db.commit()
        logging.info("=== Pipeline executado com sucesso ===")

    except Exception as e:
        db.rollback()
        logging.error(f"Erro durante a execução do pipeline: {e}", exc_info=True)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    # Carrega .env cedo para logs/pastas etc se você precisar
    load_dotenv("config.env")
    run_pipeline()
