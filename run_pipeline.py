#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline de curadoria de ofertas
- Login no Mercado Livre com Selenium (Chrome + webdriver-manager)
- Sequência de login com desafios opcionais:
    email -> captcha#1? -> senha -> captcha#2? -> qr/2FA?
- Sem input(); usa esperas automáticas
- Cookies reutilizáveis em ml_cookies.json
"""

import os
import sys
import json
import logging
import time
import datetime
from datetime import timedelta

from dotenv import load_dotenv

# ------------------------------------------------------------------
# Ajuste sys.path de acordo com sua estrutura
# ------------------------------------------------------------------
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from backend.db.database import SessionLocal
from backend.models.models import Usuario, Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta, HistoricoPreco
from backend.modules.collector import Collector
from backend.modules.validator import Validator
from backend.modules.publisher import Publisher
from backend.modules.metrics_analyzer import MetricsAnalyzer

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("./logs/pipeline.log"), logging.StreamHandler()],
)

# ------------------------------------------------------------------
# Selenium (Chrome + webdriver-manager)
# ------------------------------------------------------------------
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ------------------------------------------------------------------
# Utils: cookies + waits
# ------------------------------------------------------------------
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
    payload = {"created_at": datetime.datetime.now(datetime.UTC).isoformat(), "cookies": []}
    for c in selenium_cookies:
        payload["cookies"].append(
            {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": c.get("domain", ".mercadolivre.com.br"),
                "path": c.get("path", "/"),
                "expiry": c.get("expiry"),
                "secure": c.get("secure", True),
                "httpOnly": c.get("httpOnly", False),
            }
        )
    os.makedirs(os.path.dirname(cookies_file) or ".", exist_ok=True)
    with open(cookies_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _build_driver(headless: bool):
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,1200")
    options.add_argument("--lang=pt-BR")
    # silencia o warning de WebGL/software rasterizer
    options.add_argument("--enable-unsafe-swiftshader")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _inject_cookies(driver, cookies_file: str):
    if not os.path.exists(cookies_file):
        return
    try:
        with open(cookies_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
    except Exception:
        cookies = []
    if not cookies:
        return
    driver.get("https://www.mercadolivre.com.br/")
    for c in cookies:
        try:
            cookie = {"name": c.get("name"), "value": c.get("value"), "path": c.get("path", "/")}
            dom = c.get("domain", ".mercadolivre.com.br")
            try:
                cookie["domain"] = dom
                if c.get("expiry") is not None:
                    cookie["expiry"] = int(c["expiry"])
                driver.add_cookie(cookie)
            except Exception:
                cookie.pop("domain", None)
                driver.add_cookie(cookie)
        except Exception:
            pass


def _looks_logged_in(driver) -> bool:
    try:
        driver.get("https://www.mercadolivre.com.br/")
        time.sleep(1.2)
        page = driver.page_source.lower()
        print("looks_logged_in", "minha conta" in page, "sair" in page) # debug
        return ("minha conta" in page) or ("sair" in page)
    except Exception:
        return False


def _wait_until(fn_check, timeout_sec=180, poll_sec=1.0):
    end = time.time() + timeout_sec
    while time.time() < end:
        try:
            if fn_check():
                return True
        except Exception:
            pass
        time.sleep(poll_sec)
    return False


# ------------------------------------------------------------------
# Login com sequência: email -> captcha1? -> senha -> captcha2? -> qr/2FA?
# ------------------------------------------------------------------
def _selenium_login_and_get_cookies(
    email: str,
    password: str,
    headless: bool,
    max_wait_captcha1: int,
    max_wait_captcha2: int,
    max_wait_qr: int,
) -> list:
    """
    Fluxo sem input():
      1) Goto https://www.mercadolivre.com/jms/mlb/lgz/login
      2) Preenche e-mail e envia
      3) Aguarda campo de senha (se houve CAPTCHA#1, você resolve na janela visível)
      4) Preenche senha e envia
      5) Aguarda sessão/redirect (se houver CAPTCHA#2 ou QR/2FA, resolva durante a espera)
    Observação: para interagir com captchas/QR, rode com ML_SELENIUM_HEADLESS=False.
    """
    driver = _build_driver(headless=headless)
    wait = WebDriverWait(driver, 30)

    try:
        # 1) Login URL oficial (MLB)
        driver.get("https://www.mercadolivre.com/jms/mlb/lgz/login")

        # 2) E-mail
        email_set = False
        for by, sel in [
            (By.ID, "user_id"),
            (By.NAME, "user_id"),
            (By.CSS_SELECTOR, "input[name='user_id']"),
            (By.CSS_SELECTOR, "input[type='email']"),
        ]:
            try:
                el = wait.until(EC.presence_of_element_located((by, sel)))
                el.clear()
                el.send_keys(email)
                email_set = True
                break
            except Exception:
                continue

        if email_set:
            for by, sel in [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.ID, "login_user_form"),
            ]:
                try:
                    driver.find_element(by, sel).click()
                    break
                except Exception:
                    continue

        # 3) Espera campo de senha (CAPTCHA #1 pode aparecer nesse intervalo)
        _wait_until(
            lambda: bool(driver.find_elements(By.CSS_SELECTOR, "input[type='password'], input#password, input[name='password']")),
            timeout_sec=max_wait_captcha1,
            poll_sec=1.0,
        )

        # 4) Senha
        pwd_set = False
        for by, sel in [
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[name='password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]:
            try:
                el = WebDriverWait(driver, 20).until(EC.presence_of_element_located((by, sel)))
                el.clear()
                el.send_keys(password)
                pwd_set = True
                break
            except Exception:
                continue

        if pwd_set:
            for by, sel in [
                (By.ID, "action-complete"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
            ]:
                try:
                    driver.find_element(by, sel).click()
                    break
                except Exception:
                    continue

        # 5) Espera sessão/redirect (CAPTCHA #2 e/ou QR/2FA podem ocorrer aqui)
        _wait_until(
            lambda: (driver.current_url.startswith("https://www.mercadolivre.com.br/")),
            timeout_sec=max_wait_captcha2 + max_wait_qr,
            poll_sec=2.0,
        )

        # Verificação final
        if not _looks_logged_in(driver):
            driver.get("https://www.mercadolivre.com.br/")
            _wait_until(lambda: _looks_logged_in(driver), timeout_sec=30, poll_sec=2.0)

        cookies = driver.get_cookies()
        return cookies

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def ensure_ml_login():
    """
    Garante cookies válidos para o Mercado Livre:
      - Reutiliza cookies se criados há menos que ML_LOGIN_REUSE_DAYS.
      - Caso contrário, executa login com esperas automáticas para CAPTCHA/QR.
    """
    load_dotenv("config.env")

    email = os.getenv("ML_EMAIL", "").strip()
    password = os.getenv("ML_PASSWORD", "").strip()
    cookies_file = os.getenv("ML_COOKIES_FILE", "./ml_cookies.json")
    reuse_days = int(os.getenv("ML_LOGIN_REUSE_DAYS", "14"))

    headless = os.getenv("ML_SELENIUM_HEADLESS", "False").strip().lower() in ("1", "true", "yes")
    # timeouts (segundos) para cada etapa opcional
    max_wait_captcha1 = int(os.getenv("ML_MAX_WAIT_CAPTCHA1_SEC", "240"))
    max_wait_captcha2 = int(os.getenv("ML_MAX_WAIT_CAPTCHA2_SEC", "240"))
    max_wait_qr       = int(os.getenv("ML_MAX_WAIT_QR_SEC", "240"))

    if not email or not password:
        logging.warning("ML_EMAIL/ML_PASSWORD não configurados; seguindo sem login.")
        return

    # 1) Reutiliza cookies
    created, cookies = _load_cookies_from_file(cookies_file)
    if cookies and created and (datetime.datetime.now(datetime.UTC) - created) < timedelta(days=reuse_days):
        logging.info("Cookies do Mercado Livre reutilizados (ainda válidos).")
        return

    # 2) Login completo
    logging.info("Fazendo login no Mercado Livre com Selenium (CAPTCHA/QR opcionais).")
    cookies = _selenium_login_and_get_cookies(
        email=email,
        password=password,
        headless=headless,
        max_wait_captcha1=max_wait_captcha1,
        max_wait_captcha2=max_wait_captcha2,
        max_wait_qr=max_wait_qr,
    )

    if not cookies:
        logging.warning("Não foi possível capturar cookies de sessão.")
        return

    _save_cookies_to_file(cookies, cookies_file)
    logging.info("Login realizado e cookies salvos.")


# ------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------
def run_pipeline():
    db = SessionLocal()
    try:
        logging.info("=== Iniciando Pipeline de Curadoria de Ofertas ===")

        # 0) Login ML
        ensure_ml_login()

        # 1) Coleta
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

        # 4) Métricas
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
    load_dotenv("config.env")
    run_pipeline()
