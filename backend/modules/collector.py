import os
import re
import json
import time
from datetime import datetime
from urllib.parse import urljoin, quote

from bs4 import BeautifulSoup

# =========================
# Imports tolerantes à estrutura do projeto
# =========================
try:
    from backend.models.models import (
        Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
    )
    from backend.db.database import SessionLocal
except Exception:
    try:
        from ..models.models import (
            Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
        )
        from ..db.database import SessionLocal
    except Exception:
        try:
            from models import (
                Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
            )  # type: ignore
        except Exception:
            from model import (
                Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
            )  # type: ignore
        try:
            from database import SessionLocal  # type: ignore
        except Exception:
            from db.database import SessionLocal  # type: ignore


# =========================
# Selenium (Chrome + webdriver-manager)
# =========================
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class BrowserManager:
    """
    Gerencia um único driver Chrome (Selenium), injeta cookies salvos e expõe métodos utilitários.
    """
    def __init__(self, headless: bool, cookies_file: str):
        self.headless = headless
        self.cookies_file = cookies_file
        self._driver = None

    def _build_driver(self):
        options = ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1280,1200")
        options.add_argument("--lang=pt-BR")
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    def _load_cookies_from_file(self):
        if not os.path.exists(self.cookies_file):
            return []
        try:
            with open(self.cookies_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("cookies", [])
        except Exception:
            return []

    def _inject_cookies(self, driver):
        cookies = self._load_cookies_from_file()
        if not cookies:
            return
        # precisa estar no domínio correto para setar cookies
        driver.get("https://www.mercadolivre.com.br/")
        for c in cookies:
            try:
                cookie = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "path": c.get("path", "/"),
                }
                dom = c.get("domain", ".mercadolivre.com.br")
                # alguns chromes não aceitam domain explícito; tentamos com e sem
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

    def get(self):
        if self._driver is None:
            self._driver = self._build_driver()
            self._inject_cookies(self._driver)
        return self._driver

    def soup(self):
        from bs4 import BeautifulSoup
        return BeautifulSoup(self.get().page_source, "html.parser")

    def wait(self, timeout=20):
        return WebDriverWait(self.get(), timeout)

    def close(self):
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None


def _parse_csv_env(name: str):
    raw = os.getenv(name, "").strip()
    if not raw:
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


class Collector:
    def __init__(self, db_session):
        self.db_session = db_session

        # Parâmetros
        self.max_pages = int(os.getenv("ML_MAX_PAGES", "2"))
        self.max_products_per_page = int(os.getenv("ML_MAX_PRODUCTS_PER_PAGE", "40"))
        self.max_products_per_store = int(os.getenv("ML_MAX_PRODUCTS_PER_STORE", "120"))
        self.delay_sec = float(os.getenv("ML_REQUEST_DELAY_SEC", "1.0"))
        self.affiliate_template = os.getenv("ML_AFFILIATE_TEMPLATE", "").strip()

        # Desconto mínimo
        min_pct = os.getenv("ML_MIN_DISCOUNT_PCT")
        if min_pct is not None and min_pct != "":
            self.min_discount_pct = float(min_pct)
        else:
            real_disc = os.getenv("REAL_DISCOUNT")
            self.min_discount_pct = float(real_disc) * 100 if real_disc else 0.0

        # Cookies + Headless
        self.cookies_file = os.getenv("ML_COOKIES_FILE", "./ml_cookies.json")
        headless_str = os.getenv("ML_SELENIUM_HEADLESS", "True").strip().lower()
        self.headless = headless_str in ("1", "true", "yes")

        # Filtros (opcionais)
        self.allow_tags = _parse_csv_env("ML_ALLOW_TAGS")
        self.block_tags = _parse_csv_env("ML_BLOCK_TAGS")
        self.allow_kw = _parse_csv_env("ML_ALLOW_KEYWORDS")
        self.block_kw = _parse_csv_env("ML_BLOCK_KEYWORDS")

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        self.tag_keywords = {
            'informatica': ['notebook', 'computador', 'ssd', 'memória ram', 'memoria ram', 'processador',
                            'monitor', 'teclado', 'mouse', 'placa de vídeo', 'placa de video'],
            'gamer': ['gamer', 'rtx', 'geforce', 'radeon', 'console', 'playstation', 'xbox', 'nintendo', 'headset gamer'],
            'celular': ['iphone', 'galaxy', 'xiaomi', 'motorola', 'smartphone', 'celular', 'android', 'ios'],
            'eletrodomestico': ['geladeira', 'fogão', 'fogao', 'micro-ondas', 'microondas', 'air fryer', 'batedeira',
                                'liquidificador', 'lava-louças', 'lava loucas', 'aspirador'],
            'tv': ['tv', 'televisão', 'televisao', 'smart tv', 'qled', 'oled'],
            'audio': ['fone', 'caixa de som', 'soundbar', 'bluetooth'],
            'casa': ['cama', 'mesa', 'banho', 'sofa', 'armario', 'decoracao', 'utensilios'],
            'esporte': ['tenis', 'roupa esportiva', 'bicicleta', 'fitness', 'suplemento'],
            'livros': ['livro', 'e-book', 'ebook', 'literatura', 'ficcao', 'não ficção', 'nao ficcao'],
            'brinquedos': ['brinquedo', 'boneca', 'carrinho', 'lego', 'jogo de tabuleiro', 'jogos de tabuleiro']
        }

        self._open_statuses = {"PENDENTE_APROVACAO", "APROVADO", "AGENDADO", "PUBLICADO"}

        # Selenium browser
        self.browser = BrowserManager(headless=self.headless, cookies_file=self.cookies_file)
        self.driver = self.browser.get()

    # --------------- Utils ---------------

    def _slugify(self, text: str) -> str:
        import unicodedata
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^a-zA-Z0-9\- ]+", "", text).strip().lower()
        text = text.replace(" ", "-")
        text = re.sub(r"-{2,}", "-", text)
        return text

    def _affiliate_url(self, raw_url: str) -> str:
        if self.affiliate_template:
            try:
                return self.affiliate_template.format(url=quote(raw_url, safe=""))
            except Exception:
                return raw_url
        return raw_url

    def _suggest_tags(self, product_name):
        suggested_tags = []
        name_lower = product_name.lower()
        for tag_name, keywords in self.tag_keywords.items():
            if any(keyword in name_lower for keyword in keywords):
                tag = self.db_session.query(Tag).filter_by(nome_tag=tag_name).first()
                if not tag:
                    tag = Tag(nome_tag=tag_name)
                    self.db_session.add(tag)
                    self.db_session.commit()
                    self.db_session.refresh(tag)
                suggested_tags.append(tag)
        return suggested_tags

    def _passes_keyword_filters(self, product_name: str) -> bool:
        name = product_name.lower()
        if self.allow_kw and not any(kw in name for kw in self.allow_kw):
            return False
        if self.block_kw and any(kw in name for kw in self.block_kw):
            return False
        return True

    def _passes_tag_filters(self, tag_objs) -> bool:
        names = {t.nome_tag.lower() for t in tag_objs}
        if self.allow_tags and not (names & self.allow_tags):
            return False
        if self.block_tags and (names & self.block_tags):
            return False
        return True

    def _last_price(self, produto_id: int, loja_id: int):
        last = (
            self.db_session.query(HistoricoPreco)
            .filter(
                HistoricoPreco.produto_id == produto_id,
                HistoricoPreco.loja_id == loja_id,
            )
            .order_by(HistoricoPreco.data_verificacao.desc())
            .first()
        )
        return last.preco if last else None

    def _has_open_offer(self, produto_id: int, loja_id: int) -> bool:
        q = (
            self.db_session.query(Oferta)
            .filter(
                Oferta.produto_id == produto_id,
                Oferta.loja_id == loja_id,
                Oferta.status.in_(list(self._open_statuses)),
            )
            .limit(1)
            .all()
        )
        return len(q) > 0

    def _save_product_and_offer(self, product_data, loja_confiavel):
        desconto_pct = product_data.get('desconto') or 0.0
        if desconto_pct < self.min_discount_pct:
            return False

        if not self._passes_keyword_filters(product_data['nome_produto']):
            return False

        produto = self.db_session.query(Produto).filter_by(
            product_id_loja=product_data['product_id_loja']
        ).first()

        if not produto:
            produto = Produto(
                product_id_loja=product_data['product_id_loja'],
                nome_produto=product_data['nome_produto'],
                url_base=product_data['url_base'],
                imagem_url=product_data.get('imagem_url')
            )
            self.db_session.add(produto)
            self.db_session.flush()

            suggested = self._suggest_tags(product_data['nome_produto'])
            if not self._passes_tag_filters(suggested):
                self.db_session.rollback()
                return False
            for tag in suggested:
                produto.tags.append(tag)
            self.db_session.commit()
            self.db_session.refresh(produto)
        else:
            produto.nome_produto = product_data['nome_produto'] or produto.nome_produto
            if product_data.get('imagem_url'):
                produto.imagem_url = product_data['imagem_url']
            suggested = self._suggest_tags(product_data['nome_produto'])
            if not self._passes_tag_filters(suggested):
                self.db_session.commit()
                return False
            for tag in suggested:
                if tag not in produto.tags:
                    produto.tags.append(tag)
            self.db_session.commit()
            self.db_session.refresh(produto)

        # preço mudou?
        last_price = self._last_price(produto.id, loja_confiavel.id)
        current_price = float(product_data['preco_oferta'])
        same_price = (last_price is not None) and (abs(current_price - float(last_price)) < 1e-6)

        if self._has_open_offer(produto.id, loja_confiavel.id):
            if not same_price:
                historico = HistoricoPreco(
                    produto_id=produto.id,
                    loja_id=loja_confiavel.id,
                    preco=current_price,
                    data_verificacao=datetime.now()
                )
                self.db_session.add(historico)
                self.db_session.commit()
            return False

        if same_price:
            return False

        historico = HistoricoPreco(
            produto_id=produto.id,
            loja_id=loja_confiavel.id,
            preco=current_price,
            data_verificacao=datetime.now()
        )
        self.db_session.add(historico)

        oferta = Oferta(
            produto_id=produto.id,
            loja_id=loja_confiavel.id,
            preco_original=product_data.get('preco_original'),
            preco_oferta=current_price,
            url_afiliado_longa=self._affiliate_url(product_data['url_base']),
            data_encontrado=datetime.now(),
            data_validade=product_data.get('data_validade'),
            status="PENDENTE_APROVACAO"
        )
        self.db_session.add(oferta)
        self.db_session.commit()
        return True

    # --------------- Scrapers (Selenium) ---------------

    def _extract_mlb_id(self, url: str) -> str:
        m = re.search(r"(MLB-\d+)", url, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        return url.rstrip("/").split("/")[-1]

    def _scrape_mercadolivre_product(self, url: str):
        """Scrape de produto com Selenium (DOM renderizado)."""
        d = self.driver
        try:
            d.get(url)
            wait = WebDriverWait(d, 20)

            # título
            title = "N/A"
            for by, sel in [
                (By.CSS_SELECTOR, "h1.ui-pdp-title"),
                (By.CSS_SELECTOR, "h1"),
            ]:
                try:
                    el = wait.until(EC.presence_of_element_located((by, sel)))
                    if el and el.text.strip():
                        title = el.text.strip()
                        break
                except Exception:
                    continue

            # preço atual
            price = 0.0
            found = False
            for by, sel in [
                (By.CSS_SELECTOR, "span.andes-money-amount__fraction"),
                (By.CSS_SELECTOR, "[data-testid='price'] span.andes-money-amount__fraction"),
            ]:
                try:
                    el = d.find_element(by, sel)
                    txt = el.text.strip()
                    if txt:
                        price = float(txt.replace('.', '').replace(',', '.'))
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                # às vezes o preço aparece após um pequeno atraso
                time.sleep(0.6)
                try:
                    el = d.find_element(By.CSS_SELECTOR, "span.andes-money-amount__fraction")
                    txt = el.text.strip()
                    if txt:
                        price = float(txt.replace('.', '').replace(',', '.'))
                except Exception:
                    pass

            # preço original (riscado)
            original_price = price
            for by, sel in [
                (By.CSS_SELECTOR, "s .andes-money-amount__fraction"),
                (By.CSS_SELECTOR, "s.andes-money-amount__fraction"),
                (By.CSS_SELECTOR, "s span.andes-money-amount__fraction"),
            ]:
                try:
                    el = d.find_element(by, sel)
                    txt = el.text.strip()
                    if txt:
                        original_price = float(txt.replace('.', '').replace(',', '.'))
                        break
                except Exception:
                    continue

            # imagem principal
            image_url = None
            for by, sel in [
                (By.CSS_SELECTOR, "img.ui-pdp-image"),
                (By.CSS_SELECTOR, "figure.ui-pdp-gallery__figure img"),
                (By.CSS_SELECTOR, "img"),
            ]:
                try:
                    img = d.find_element(by, sel)
                    src = img.get_attribute("src")
                    if src and src.startswith("http"):
                        image_url = src
                        break
                except Exception:
                    continue

            discount = ((original_price - price) / original_price) * 100 if original_price > 0 else 0.0
            product_id_loja = self._extract_mlb_id(url) or url

            return {
                'product_id_loja': product_id_loja,
                'nome_produto': title,
                'preco_oferta': price,
                'preco_original': original_price,
                'desconto': discount,
                'url_base': url,
                'imagem_url': image_url,
                'data_validade': None,
            }
        except Exception as e:
            print(f"[ML PRODUTO] Falha em {url}: {e}")
            return None

    def _extract_product_links_from_store(self, html: str):
        """Extrai links de produto do HTML da loja (heurística robusta)."""
        soup = BeautifulSoup(html, 'html.parser')
        links, seen = [], set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if ('produto.mercadolivre.com' in href) or re.search(r'/MLB-\d', href, flags=re.IGNORECASE):
                if href.startswith('/'):
                    href = urljoin('https://www.mercadolivre.com.br', href)
                href = href.split('#')[0]
                if href not in seen:
                    seen.add(href)
                    links.append(href)
        return links

    def _scrape_ml_store(self, loja: LojaConfiavel):
        slug = (loja.id_loja_api or self._slugify(loja.nome_loja)).strip('/')
        base_url = f"https://www.mercadolivre.com.br/loja/{slug}"
        total_salvos = 0
        print(f"[ML LOJA] Coletando: {loja.nome_loja} -> {base_url}")

        d = self.driver

        for page_num in range(1, self.max_pages + 1):
            if total_salvos >= self.max_products_per_store:
                break

            url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
            try:
                d.get(url)
                # pequena espera para a grade renderizar
                d.implicitly_wait(2)
                html = d.page_source
            except Exception as e:
                print(f"[ML LOJA] Erro ao abrir {url}: {e}")
                break

            product_links = self._extract_product_links_from_store(html)
            if not product_links:
                if page_num == 1:
                    print(f"[ML LOJA] Nenhum produto encontrado na loja {loja.nome_loja}. Verifique o slug/HTML.")
                break

            product_links = product_links[: self.max_products_per_page]
            print(f"[ML LOJA] Página {page_num}: {len(product_links)} produtos (limitados)")

            for link in product_links:
                if total_salvos >= self.max_products_per_store:
                    break

                data = self._scrape_mercadolivre_product(link)
                if not data:
                    time.sleep(self.delay_sec)
                    continue

                try:
                    created = self._save_product_and_offer(data, loja)
                    if created:
                        total_salvos += 1
                        print(f"[ML LOJA] Salvo: {data['nome_produto'][:80]}... ({data['desconto']:.1f}% off)")
                    else:
                        print(f"[ML LOJA] Ignorado (filtros/duplicado/sem mudança): {data['nome_produto'][:80]}")
                except Exception as e:
                    print(f"[ML LOJA] Falha ao salvar oferta ({link}): {e}")

                time.sleep(self.delay_sec)

            time.sleep(self.delay_sec)

        print(f"[ML LOJA] Concluído {loja.nome_loja}. Ofertas salvas: {total_salvos}")

    # --------------- Orquestração ---------------

    def run_collection(self):
        print("Iniciando coleta de ofertas por lojas Mercado Livre (Selenium, autenticado via cookies)...")
        lojas_confiaveis = self.db_session.query(LojaConfiavel).filter_by(ativa=True).all()

        for loja in lojas_confiaveis:
            plataforma = (loja.plataforma or "").strip().lower()
            if plataforma in ("mercado livre", "mercadolivre", "ml"):
                self._scrape_ml_store(loja)
            else:
                print(f"[SKIP] Plataforma não suportada ainda: {loja.plataforma} ({loja.nome_loja})")

        print("Coleta concluída.")

    def close(self):
        try:
            self.browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    db = SessionLocal()
    collector = None
    try:
        collector = Collector(db)
        collector.run_collection()
    finally:
        try:
            if collector:
                collector.close()
        except Exception:
            pass
        db.close()
