from __future__ import annotations

import os
import time
import random
from typing import Callable, Iterable, Optional, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from backend.modules.utils.config import get_config


class SeleniumClient:
    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        profile_dir: Optional[str] = None,
        detach: bool = False,
        delay_sec: float = float(get_config("SELENIUM_DELAY_SEC", "2")),
        log_error: Optional[Callable[[str, str, str, dict, dict], None]] = None,
    ):
        self._delay_sec = delay_sec
        self._detach = detach
        self._user_data_dir = (user_data_dir or "").strip()
        self._profile_dir = (profile_dir or "").strip()
        self._driver = None
        self._log_error = log_error
        
        # Evitar usar o diretório padrão do Chrome diretamente
        self._DEFAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
        if self._user_data_dir:
            expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(self._user_data_dir)))
            if os.path.normcase(expanded) == os.path.normcase(os.path.abspath(self._DEFAULT_DIR)):
                safe_dir = os.path.join(os.path.dirname(self._DEFAULT_DIR), "ChromeSelenium")
                os.makedirs(safe_dir, exist_ok=True)
                self._user_data_dir = safe_dir
            else:
                self._user_data_dir = expanded

    # ============== Driver ==============
    def _build_chrome_options(self) -> ChromeOptions:
        options = ChromeOptions()
        if self._detach:
            options.add_experimental_option("detach", True)
        options.add_argument("--lang=pt-BR")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if self._user_data_dir:
            for f in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                if os.path.exists(os.path.join(self._user_data_dir, f)):
                    raise RuntimeError(f"Perfil em uso em '{self._user_data_dir}'. Feche TODO o Chrome e tente novamente.")
            options.add_argument(f"--user-data-dir={self._user_data_dir}")
            if self._profile_dir:
                options.add_argument(f"--profile-directory={self._profile_dir}")
        return options

    def _get_driver(self):
        if self._driver is not None:
            return self._driver
        service = Service()  # Selenium Manager localiza o chromedriver
        self._driver = webdriver.Chrome(service=service, options=self._build_chrome_options())
        try:
            self._driver.maximize_window()
        except Exception:
            pass
        return self._driver

    def close(self):
        try:
            if self._driver:
                self._driver.quit()
        except Exception:
            pass
        self._driver = None

    # ============== Navegação ==============
    def get_page(
        self,
        url: str,
        wait_any_css: Optional[Iterable[str]] = None,
        wait_any_xpath: Optional[Iterable[str]] = None,
        wait_any_id: Optional[Iterable[str]] = None,
        timeout_sec: int = 25,
        sleep_before: Tuple[float, float] = (0.25, 0.9),
    ) -> str:
        """
        Abre a URL, espera qualquer seletor (CSS/XPath) e retorna page_source.
        """
        driver = self._get_driver()
        driver.get(url)
        time.sleep(timeout_sec + random.uniform(*sleep_before))

        conditions = []
        if wait_any_css:
            for css in wait_any_css:
                conditions.append(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
        if wait_any_xpath:
            for xp in wait_any_xpath:
                conditions.append(EC.presence_of_element_located((By.XPATH, xp)))
        if wait_any_id:
            for id in wait_any_id:
                conditions.append(EC.presence_of_element_located((By.ID, id)))

        if conditions:
            try:
                WebDriverWait(driver, timeout_sec).until(EC.any_of(*conditions))
            except Exception as e_wait:
                self._safe_log(url, f"Timeout esperando elementos: {e_wait}", "WAIT_GET_PAGE")

        #time.sleep(self._delay_sec + random.uniform(*sleep_before))
        return driver.page_source

    def get_short_affiliate_url(
        self,
        soup: BeautifulSoup,
        delay: int = 25,
    ) -> Optional[str]:
         """
         Usa a página já aberta:
         - Verifica no HTML (soup) se existe o span 'Compartilhar'
         - Clica no botão correspondente
         - Espera o textarea[data-testid='text-field__label_link'] e retorna seu valor
         Não navega novamente.
         """
         if soup is None:
             return None
         
 
         # Verifica presença do span 'Compartilhar' no HTML já carregado
         share_present = False
         try:
             for sp in soup.find_all("span"):
                 classes = sp.get("class") or []
                 if ("andes-button__text" in classes) and (sp.get_text(strip=True) == "Compartilhar"):
                     share_present = True
                     break
         except Exception:
             share_present = False
         if not share_present:
             return None
         
 
         driver = self._get_driver()
         try:
             # Localiza o span via XPath e sobe ao botão
             share_span = WebDriverWait(driver, 6).until(
                 EC.presence_of_element_located(
                     (By.XPATH, "//span[contains(@class,'andes-button__text') and normalize-space()='Compartilhar']")
                 )
             )
             try:
                 share_button = share_span.find_element(By.XPATH, "ancestor::button[1]")
             except Exception:
                 share_button = share_span
 
             # Clica no botão
             try:
                 share_button.click()
             except Exception:
                 try:
                     driver.execute_script("arguments[0].click();", share_button)
                 except Exception:
                     return None
 
             time.sleep(delay + random.uniform(0.25, 0.9))
 
             # Espera o textarea com o link curto
             textarea = WebDriverWait(driver, 8).until(
                 EC.presence_of_element_located(
                     (By.CSS_SELECTOR, "textarea[data-testid='text-field__label_link']")
                 )
             )
             val = (textarea.get_attribute("value") or "").strip() or (textarea.text or "").strip()
             return val if val.startswith("http") else None
         except Exception:
             return None

    def export_session_state(self, base_url: str) -> dict:
        """
        Exporta cookies (via CDP) e localStorage do domínio base.
        """
        driver = self._get_driver()
        # Cookies de todos domínios (CDP)
        try:
            cookies_all = driver.execute_cdp_cmd("Network.getAllCookies", {})  # {'cookies': [...]}
        except Exception:
            cookies_all = {"cookies": []}

        # LocalStorage do domínio base
        ls_items = {}
        try:
            driver.get(base_url)
            #time.sleep(self._delay_sec + random.uniform(0.1, 0.3))
            entries = driver.execute_script("return Object.entries(window.localStorage);") or []
            ls_items = {k: v for k, v in entries}
        except Exception:
            ls_items = {}
        return {"cookies": cookies_all.get("cookies", []), "localStorage": ls_items}

    def import_session_state(self, base_url: str, state: dict) -> None:
        """
        Importa cookies (CDP) e localStorage no driver atual.
        """
        driver = self._get_driver()
        cookies = (state or {}).get("cookies") or []
        # Seta cookies via CDP (não precisa estar na página certa)
        try:
            driver.execute_cdp_cmd("Network.setCookies", {"cookies": cookies})
        except Exception:
            # fallback silencioso; ainda tentaremos localStorage
            pass

        # Agora aplica localStorage no domínio base
        try:
            driver.get(base_url)
            #time.sleep(self._delay_sec + random.uniform(0.1, 0.3))
            if state.get("localStorage"):
                # limpa e injeta
                driver.execute_script("window.localStorage.clear();")
                for k, v in state["localStorage"].items():
                    driver.execute_script("window.localStorage.setItem(arguments[0], arguments[1]);", k, v)
                # reload para sessão aplicar
                driver.refresh()
                #time.sleep(self._delay_sec + random.uniform(0.1, 0.2))
        except Exception:
            pass

    # ============== Log helper ==============
    def _safe_log(self, product_url: str, mensagem: str, etapa: str):
        try:
            if self._log_error:
                self._log_error(product_url, mensagem, etapa, {}, {})
        except Exception:
            pass