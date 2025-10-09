import argparse
import os
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from backend.modules.utils.config import get_config

# URL alvo (produto catalogado do ML)
TARGET_URL = "https://www.mercadolivre.com.br/p/MLB44113908"

def build_chrome_options(args: argparse.Namespace) -> ChromeOptions:
    """
    Configurações do Chrome:
    - idioma pt-BR
    - mantém a janela aberta (detach)
    - opcional: reutilizar seu perfil do Chrome (reduz challenge/bloqueios)
    """
    options = ChromeOptions()
    # Mantém o Chrome aberto ao final (útil para inspeção)
    options.add_experimental_option("detach", True)

    # Idioma pt-BR (algumas renderizações/formatos variam por idioma)
    options.add_argument("--lang=pt-BR")

    # Dicas que costumam reduzir alguns 'fingerprints' de automação
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Se quiser ver logs menos verbosos:
    # options.add_argument("--log-level=3")

    # Reutilizar o perfil real do usuário (mais "humano"):
    if args.use_profile or args.user_data_dir or args.profile_dir:
        user_data_dir = (
            args.user_data_dir
            or get_config("SELENIUM_USER_DATA_DIR", "") or ""
        ).strip()
        print(f"Usando perfil do Chrome em: {user_data_dir or '(padrão)'}")
        profile_dir = get_config("SELENIUM_PROFILE_DIR", "") or ""
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_dir}")
    else:
        print("Usando perfil efêmero (sem login).")
        user_data_dir = (
            args.user_data_dir
            or get_config("SELENIUM_USER_DATA_DIR", "") or ""
        ).strip()
        print(f"Usando perfil do Chrome em: {user_data_dir or '(padrão)'}")
        profile_dir = get_config("SELENIUM_PROFILE_DIR", "") or ""
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_dir}")

    # Se o Chrome não estiver no caminho padrão, descomente e ajuste:
    # options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    return options


def wait_first(driver, locators, timeout=20):
    """
    Tenta esperar pelo primeiro locator que aparecer.
    locators = lista de tuplas (By, seletor).
    Retorna (element, locator) ou (None, None) se não achar.
    """
    end_time = time.time() + timeout
    last_err = None
    while time.time() < end_time:
        for by, sel in locators:
            try:
                el = WebDriverWait(driver, 2).until(EC.presence_of_element_located((by, sel)))
                return el, (by, sel)
            except Exception as e:
                last_err = e
        time.sleep(0.25)
    return None, None


def extract_text_or_none(driver, candidates):
    """
    Tenta vários seletores e retorna o texto do primeiro que encontrar.
    """
    el, used = wait_first(driver, candidates, timeout=15)
    if el:
        try:
            return el.text.strip()
        except Exception:
            return None
    return None


def scrape_product(driver):
    """
    Extrai alguns campos básicos do produto.
    Os seletores têm variações porque o ML muda classes com frequência.
    """
    # Título do produto (variações comuns)
    title_candidates = [
        (By.XPATH, "//h1[contains(@class,'ui-pdp-title')]"),
        (By.XPATH, "//h1[contains(@class,'poly-component__title')]"),
        (By.CSS_SELECTOR, "h1[data-testid='poly-title']"),
    ]

    # Preço (fração e centavos) – tentamos alguns padrões
    price_candidates = [
        # Preço já "inteiro"
        (By.CSS_SELECTOR, "span.price-tag-fraction"),
        (By.CSS_SELECTOR, "span.andes-money-amount__fraction"),
        (By.XPATH, "//span[contains(@class,'price-tag-text')]"),
    ]
    cents_candidates = [
        (By.CSS_SELECTOR, "span.price-tag-cents"),
        (By.CSS_SELECTOR, "span.andes-money-amount__cents"),
    ]

    title = extract_text_or_none(driver, title_candidates)

    # Preço pode vir fracionado (fraction + cents)
    price_main = extract_text_or_none(driver, price_candidates)
    price_cents = extract_text_or_none(driver, cents_candidates)

    if price_main:
        price_text = price_main
        if price_cents:
            price_text = f"{price_main},{price_cents.zfill(2)}"
    else:
        price_text = None

    # Vendedor (nem sempre disponível de cara)
    seller_candidates = [
        (By.XPATH, "//a[contains(@href,'/perfil/')]"),
        (By.CSS_SELECTOR, "a[data-testid='seller-link']"),
        (By.XPATH, "//p[contains(@class,'ui-pdp-seller__name')]"),
    ]
    seller = extract_text_or_none(driver, seller_candidates)

    # Disponibilidade / estoque (opcional)
    stock_candidates = [
        (By.XPATH, "//*[contains(text(),'unidades disponíveis')]"),
        (By.XPATH, "//*[contains(text(),'unidade disponível')]"),
        (By.CSS_SELECTOR, "[data-testid='available-quantity']"),
    ]
    stock_text = extract_text_or_none(driver, stock_candidates)

    return {
        "title": title,
        "price": price_text,
        "seller": seller,
        "stock_info": stock_text,
        "url": driver.current_url,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scraper Selenium - Mercado Livre (produto /p/)"
    )
    parser.add_argument(
        "--url",
        default=TARGET_URL,
        help="URL do produto (ex: https://www.mercadolivre.com.br/p/MLB44113908)",
    )
    parser.add_argument(
        "--use-profile",
        action="store_true",
        help="Reutiliza o perfil padrão do seu Chrome (feche o Chrome antes).",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Caminho do diretório de dados do Chrome (ex: %LOCALAPPDATA%\\Google\\Chrome\\User Data).",
    )
    parser.add_argument(
        "--profile-dir",
        default=None,
        help="Nome do perfil do Chrome (ex: Default, Profile 1, etc.).",
    )
    args = parser.parse_args()

    options = build_chrome_options(args)

    # Selenium Manager (Selenium 4.6+) resolve o ChromeDriver automaticamente.
    # Se preferir usar webdriver-manager, dá pra trocar pelo caminho retornado.
    service = Service()

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print("\n[ERRO] Falha ao iniciar o Chrome com Selenium.")
        print("Dicas:")
        print(" - Verifique se o Google Chrome está instalado.")
        print(" - Atualize o Selenium: pip install --upgrade selenium")
        print(" - Instale o webdriver-manager: pip install webdriver-manager")
        print(" - Feche TODAS as janelas do Chrome se estiver usando --use-profile.\n")
        raise

    driver.maximize_window()
    driver.get(args.url)

    # Aguarda algum conteúdo real da página carregar
    # (um dos candidatos ao título ou algum container típico)
    anchor_candidates = [
        (By.CSS_SELECTOR, "main"),
        (By.XPATH, "//h1"),
        (By.CSS_SELECTOR, "[data-testid='poly-title']"),
    ]
    el, used = wait_first(driver, anchor_candidates, timeout=25)
    if not el:
        print("[aviso] Conteúdo principal não apareceu a tempo. Tentando mesmo assim...")

    # Faz a coleta
    data = scrape_product(driver)

    # Salva um print para auditoria/depuração
    out_png = Path("screenshot_ml_produto.png")
    try:
        driver.save_screenshot(str(out_png))
    except Exception:
        pass

    print("\n=== Resultado ===")
    for k, v in data.items():
        print(f"{k}: {v}")

    if out_png.exists():
        print(f"\nScreenshot salvo em: {out_png.resolve()}")

    # Dica: mantenho o Chrome aberto (por causa do 'detach=True').
    # Se quiser fechar ao final, descomente a linha abaixo:
    # driver.quit()


if __name__ == "__main__":
    main()
