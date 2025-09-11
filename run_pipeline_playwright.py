#!/usr/bin/env python3
"""
Pipeline completo de curadoria de ofertas
- Passo de login no Mercado Livre com Playwright (cookies reutilizáveis)
- Salva cookies em JSON (compatível com collector.py e demais módulos)
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv

# Ajuste de path (raiz do projeto)
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# ---- Imports do seu projeto (ajuste se necessário) ----
from backend.db.database import SessionLocal
from backend.models.models import Usuario, Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta, HistoricoPreco
from backend.modules.collector import Collector
from backend.modules.validator import Validator
from backend.modules.publisher import Publisher
from backend.modules.metrics_analyzer import MetricsAnalyzer

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./logs/pipeline.log"),
        logging.StreamHandler()
    ]
)

# ----------------------------------------------------------------------------
# Utilitários de Cookies (persistência em arquivo)
# ----------------------------------------------------------------------------
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

def _save_cookies_to_file(playwright_cookies: list, cookies_file: str):
    """Salva cookies (lista do Playwright) no formato comum do projeto."""
    payload = {
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "cookies": []
    }
    for c in playwright_cookies:
        payload["cookies"].append({
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".mercadolivre.com.br"),
            "path": c.get("path", "/"),
            # Playwright usa "expires" (epoch float). Mantemos como "expiry"
            "expiry": c.get("expires"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        })
    os.makedirs(os.path.dirname(cookies_file) or ".", exist_ok=True)
    with open(cookies_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

# ----------------------------------------------------------------------------
# Login com Playwright
# ----------------------------------------------------------------------------
def _playwright_login_and_get_cookies(email: str, password: str, headless: bool = True, manual_wait_ms: int = 90000):
    """
    Abre o Chromium via Playwright, realiza o login e retorna os cookies do contexto.
    Se houver CAPTCHA/2FA e headless=False, dá uma janela (manual_wait_ms) para você concluir.
    Dependências:
      pip install playwright
      playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception as e:
        raise RuntimeError(
            "Playwright não está instalado. Rode:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from e

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, args=[
            "--no-sandbox",
            "--disable-gpu",
            "--lang=pt-BR"
        ])
        context = browser.new_context(
            viewport={"width": 1280, "height": 1200},
            locale="pt-BR"
        )
        page = context.new_page()

        try:
            page.goto("https://www.mercadolivre.com/jms/mlb/lgz/login", timeout=30000, wait_until="load")

            # 1) Digita email
            filled_email = False
            for sel in ["input#user_id", "input[name='user_id']", "input[type='email']"]:
                try:
                    page.wait_for_selector(sel, timeout=5000)
                    page.fill(sel, email)
                    filled_email = True
                    break
                except PWTimeout:
                    continue

            if filled_email:
                for btn in ["button[type='submit']", "input[type='submit']", "#login_user_form button[type='submit']"]:
                    try:
                        page.click(btn, timeout=2000)
                        break
                    except Exception:
                        continue

            # 2) Digita senha
            filled_pwd = False
            for sel in ["input#password", "input[name='password']", "input[type='password']"]:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    page.fill(sel, password)
                    filled_pwd = True
                    break
                except PWTimeout:
                    continue

            if filled_pwd:
                for btn in ["#action-complete", "button[type='submit']", "input[type='submit']"]:
                    try:
                        page.click(btn, timeout=3000)
                        break
                    except Exception:
                        continue

            # 3) Espera redirect básico
            try:
                page.wait_for_timeout(3000)
                page.goto("https://www.mercadolivre.com.br/", timeout=30000, wait_until="load")
                page.wait_for_timeout(1500)
            except Exception:
                pass

            # Se ainda não logado (ex.: 2FA/CAPTCHA), permitir intervenção manual se não headless
            if not headless:
                page.wait_for_timeout(manual_wait_ms)

            cookies = context.cookies()
            return cookies
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

def ensure_ml_login_playwright():
    """
    Garante cookies válidos para o Mercado Livre usando Playwright.
    - Se cookies "frescos" existem (idade < ML_LOGIN_REUSE_DAYS), apenas mantém.
    - Caso contrário, faz login com Playwright e salva novos cookies.
    """
    load_dotenv("config.env")

    email = os.getenv("ML_EMAIL", "").strip()
    password = os.getenv("ML_PASSWORD", "").strip()
    cookies_file = os.getenv("ML_COOKIES_FILE", "./ml_cookies.json")
    reuse_days = int(os.getenv("ML_LOGIN_REUSE_DAYS", "14"))
    headless = os.getenv("ML_PLAYWRIGHT_HEADLESS", os.getenv("ML_SELENIUM_HEADLESS", "True")).strip().lower() in ("1", "true", "yes")

    if not email or not password:
        logging.warning("ML_EMAIL/ML_PASSWORD não configurados; seguindo sem login.")
        return

    created, cookies = _load_cookies_from_file(cookies_file)
    if cookies and created and (datetime.datetime.now(datetime.UTC) - created) < timedelta(days=reuse_days):
        logging.info("Cookies do Mercado Livre reutilizados (Playwright).")
        return

    logging.info("Fazendo login no Mercado Livre via Playwright…")
    cookies = _playwright_login_and_get_cookies(email, password, headless=headless)
    if not cookies:
        logging.warning("Não foi possível obter cookies via Playwright. Verifique credenciais/2FA.")
        return

    _save_cookies_to_file(cookies, cookies_file)
    logging.info("Login realizado e cookies salvos (Playwright).")

# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def run_pipeline():
    db = SessionLocal()
    try:
        logging.info("=== Iniciando Pipeline de Curadoria de Ofertas ===")

        # 0) Login ML (gera/valida cookies antes da coleta) via Playwright
        ensure_ml_login_playwright()

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
