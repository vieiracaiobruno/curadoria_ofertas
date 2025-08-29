import os
import re
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, quote

import requests
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
            from models import (
                Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
            )  # type: ignore
        try:
            from database import SessionLocal  # type: ignore
        except Exception:
            from db.database import SessionLocal  # type: ignore


# =========================
# Helpers Selenium (login ML)
# =========================
def _maybe_import_selenium():
    """Importa selenium e drivers sob demanda, para não quebrar se não estiver instalado."""
    from importlib import import_module
    selenium = import_module("selenium")
    webdriver = import_module("selenium.webdriver")
    expected_conditions = import_module("selenium.webdriver.support.expected_conditions")
    By = import_module("selenium.webdriver.common.by").By
    WebDriverWait = import_module("selenium.webdriver.support.ui").WebDriverWait
    # webdriver-manager
    ChromeDriverManager = import_module("webdriver_manager.chrome").ChromeDriverManager
    # undetected-chromedriver (melhora contra bloqueios)
    uc = import_module("undetected_chromedriver")
    return selenium, webdriver, expected_conditions, By, WebDriverWait, ChromeDriverManager, uc


def _save_cookies_to_file(session_cookies, cookies_file: str):
    data = {
        "created_at": datetime.utcnow().isoformat(),
        "cookies": []
    }
    for c in session_cookies:
        data["cookies"].append({
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".mercadolivre.com.br"),
            "path": c.get("path", "/"),
            "expiry": c.get("expiry"),  # pode ser None
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        })
    with open(cookies_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_cookies_from_file(cookies_file: str):
    if not os.path.exists(cookies_file):
        return None, None
    with open(cookies_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    created = None
    try:
        created = datetime.fromisoformat(data.get("created_at"))
    except Exception:
        pass
    return created, data.get("cookies", [])


def _add_cookies_to_requests_session(req_sess: requests.Session, cookies: list):
    for c in cookies:
        # requests espera expires como int (segundos Unix) ou None
        cookie_kwargs = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".mercadolivre.com.br"),
            "path": c.get("path", "/")
        }
        if c.get("expiry") is not None:
            cookie_kwargs["expires"] = c.get("expiry")
        req_sess.cookies.set(**cookie_kwargs)


def _selenium_login_and_get_cookies(email: str, password: str, headless: bool = True) -> list:
    """
    Abre navegador, faz login no ML e retorna cookies (lista de dicts no formato selenium).
    Se houver 2FA/CAPTCHA, rode headless=False e finalize manualmente; os cookies serão capturados.
    """
    (selenium, webdriver, EC, By, WebDriverWait, ChromeDriverManager, uc) = _maybe_import_selenium()

    # Preferir undetected-chromedriver
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,1200")
    options.add_argument("--lang=pt-BR")
    driver = uc.Chrome(options=options)

    try:
        # Ir direto à página de login
        login_url = "https://www.mercadolivre.com.br/hub/identity-login"
        driver.get(login_url)

        wait = WebDriverWait(driver, 30)

        # Fluxo do ML costuma ter input de email -> continuar -> input de senha -> entrar
        # Tentar múltiplos seletores para robustez
        def _type_and_continue_email():
            # Possíveis seletores de email:
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

            # Botão continuar:
            btn_candidates = [
                (By.ID, "login_user_form"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
            ]
            for by, sel in btn_candidates:
                try:
                    btn = driver.find_element(by, sel)
                    btn.click()
                    return True
                except Exception:
                    continue
            return False

        def _type_and_submit_password():
            candidates = [
                (By.ID, "password"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, "input[name='password']"),
                (By.CSS_SELECTOR, "input[type='password']"),
            ]
            pwd_input = None
            for by, sel in candidates:
                try:
                    pwd_input = wait.until(EC.presence_of_element_located((by, sel)))
                    break
                except Exception:
                    continue
            if not pwd_input:
                return False
            pwd_input.clear()
            pwd_input.send_keys(password)

            # Botão entrar:
            btn_candidates = [
                (By.ID, "action-complete"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
            ]
            for by, sel in btn_candidates:
                try:
                    btn = driver.find_element(by, sel)
                    btn.click()
                    return True
                except Exception:
                    continue
            return False

        _type_and_continue_email()
        time.sleep(2)
        _type_and_submit_password()

        # Espera um redirect simples para homepage ou conta
        time.sleep(5)
        # Heurística: cookies devem conter algo de sessão
        selenium_cookies = driver.get_cookies()
        if not selenium_cookies:
            # Deixa o user logar manualmente (captcha/2FA). Feche o modal/captcha e prossiga.
            if not headless:
                print("[ML LOGIN] Aguardando login manual (captcha/2FA). Você tem 90s...")
                time.sleep(90)
                selenium_cookies = driver.get_cookies()

        return selenium_cookies
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _ensure_logged_session(email: str, password: str, headless: bool, cookies_file: str, reuse_days: int) -> requests.Session:
    """
    Garante uma sessão requests **logada** no Mercadolivre:
    - Reutiliza cookies (se não expirados) do arquivo.
    - Caso contrário, abre Selenium para logar e salva cookies.
    - Retorna `requests.Session` pronto para uso.
    """
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

    created, cookies = _load_cookies_from_file(cookies_file)
    if cookies and created and (datetime.utcnow() - created) < timedelta(days=reuse_days):
        _add_cookies_to_requests_session(sess, cookies)

        # teste rápido: acessar homepage e ver se não vem tela de login
        try:
            r = sess.get("https://www.mercadolivre.com.br/", timeout=15)
            if r.status_code == 200 and "Minha conta" in r.text or "Minha Conta" in r.text or "Sair" in r.text:
                return sess
        except Exception:
            pass
        # cookies parecem inválidos -> re-login
        sess.cookies.clear()

    # login via selenium
    selenium_cookies = _selenium_login_and_get_cookies(email, password, headless=headless)
    if not selenium_cookies:
        print("[ML LOGIN] Não foi possível obter cookies via Selenium. Verifique credenciais/2FA.")
        return sess

    # salva e injeta na sessão requests
    _save_cookies_to_file(selenium_cookies, cookies_file)

    # converter cookies selenium -> requests
    req_cookies = []
    for c in selenium_cookies:
        req_cookies.append({
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".mercadolivre.com.br"),
            "path": c.get("path", "/"),
            "expiry": c.get("expiry"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        })
    _add_cookies_to_requests_session(sess, req_cookies)
    return sess


class Collector:
    def __init__(self, db_session):
        self.db_session = db_session

        # Parâmetros via ENV (com defaults sensatos)
        self.max_pages = int(os.getenv("ML_MAX_PAGES", "2"))
        self.max_products_per_page = int(os.getenv("ML_MAX_PRODUCTS_PER_PAGE", "40"))
        self.max_products_per_store = int(os.getenv("ML_MAX_PRODUCTS_PER_STORE", "120"))
        self.delay_sec = float(os.getenv("ML_REQUEST_DELAY_SEC", "1.0"))
        self.affiliate_template = os.getenv("ML_AFFILIATE_TEMPLATE", "").strip()

        # Desconto mínimo aceito (em %) — prioridade para ML_MIN_DISCOUNT_PCT; fallback: REAL_DISCOUNT (0-1)
        min_pct = os.getenv("ML_MIN_DISCOUNT_PCT")
        if min_pct is not None and min_pct != "":
            self.min_discount_pct = float(min_pct)
        else:
            real_disc = os.getenv("REAL_DISCOUNT")
            self.min_discount_pct = float(real_disc) * 100 if real_disc else 0.0

        # Credenciais + cookies
        self.ml_email = os.getenv("ML_EMAIL", "").strip()
        self.ml_password = os.getenv("ML_PASSWORD", "").strip()
        self.cookies_file = os.getenv("ML_COOKIES_FILE", "./ml_cookies.json")
        self.reuse_days = int(os.getenv("ML_LOGIN_REUSE_DAYS", "14"))
        headless_str = os.getenv("ML_SELENIUM_HEADLESS", "True").strip().lower()
        self.headless = headless_str in ("1", "true", "yes")

        # Sessão autenticada (criada sob demanda no primeiro uso)
        self._authed_session = None

        # Cabeçalhos HTTP (fallback; requests.Session já atualiza)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "close",
        }

        # Sugestão de tags simples por palavra-chave
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

        # Status que consideramos “em aberto” para evitar duplicatas de ofertas
        self._open_statuses = {"PENDENTE_APROVACAO", "APROVADO", "AGENDADO", "PUBLICADO"}

        # Filtros por nome/tag (mantidos do ajuste anterior)
        self.allow_tags = set()
        self.block_tags = set()
        self.allow_kw = set()
        self.block_kw = set()

    # --------------------- AUTH ---------------------

    def _session(self) -> requests.Session:
        print("[ML AUTH] Garantindo sessão autenticada no Mercado Livre...")
        if self._authed_session is None:
            if not self.ml_email or not self.ml_password:
                raise RuntimeError("Defina ML_EMAIL e ML_PASSWORD no config.env para autenticar no Mercado Livre.")
            self._authed_session = _ensure_logged_session(
                self.ml_email, self.ml_password, self.headless, self.cookies_file, self.reuse_days
            )
        return self._authed_session

    # --------------------- UTIL ---------------------

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
        print(f"[ML SALVAR] Produto: {product_data['nome_produto'][:60]}... Desconto: {desconto_pct:.1f}%") # breakpoint
        if desconto_pct < self.min_discount_pct:
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
            for tag in self._suggest_tags(product_data['nome_produto']):
                produto.tags.append(tag)
            self.db_session.commit()
            self.db_session.refresh(produto)
        else:
            produto.nome_produto = product_data['nome_produto'] or produto.nome_produto
            if product_data.get('imagem_url'):
                produto.imagem_url = product_data['imagem_url']
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

    # --------------------- SCRAPERS ---------------------

    def _extract_mlb_id(self, url: str) -> str:
        m = re.search(r"(MLB-\d+)", url, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        return url.rstrip("/").split("/")[-1]

    def _scrape_mercadolivre_product(self, url):
        """Scrape de uma página de produto individual do Mercado Livre (autenticado)."""
        try:
            r = self._session().get(url, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.content, 'html.parser')
            print(f"[ML PRODUTO] Acessando {r.content}") # breakpoint

            # Título
            title_el = soup.find('h1', {'class': re.compile(r'ui-pdp-title')})
            title = title_el.get_text(strip=True) if title_el else 'N/A'

            # Preço atual
            price_fraction = soup.find('span', {'class': re.compile(r'andes-money-amount__fraction')})
            price = 0.0
            if price_fraction:
                price = float(price_fraction.get_text(strip=True).replace('.', '').replace(',', '.'))

            # Preço original (se riscado)
            original_fraction = soup.find('s', {'class': re.compile(r'andes-money-amount__fraction')})
            original_price = float(original_fraction.get_text(strip=True).replace('.', '').replace(',', '.')) if original_fraction else price

            # Imagem principal
            image_el = soup.select_one('img.ui-pdp-image, figure.ui-pdp-gallery__figure img')
            image_url = image_el['src'] if image_el and image_el.has_attr('src') else None

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

    def _extract_product_links_from_store(self, soup):
        """Extrai links de produto a partir do HTML de uma loja do ML (heurística simples)."""
        links = []
        seen = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if ('produto.mercadolivre.com' in href) or re.search(r'/MLB\d', href, flags=re.IGNORECASE):
                if href.startswith('/'):
                    href = urljoin('https://www.mercadolivre.com.br', href)
                href = href.split('#')[0]
                if href not in seen:
                    seen.add(href)
                    links.append(href)
        return links

    def _scrape_ml_store(self, loja: LojaConfiavel):
        """
        Percorre as páginas da loja no Mercado Livre e coleta produtos (logado).
        Respeita max_pages, max_products_per_page e max_products_per_store.
        """
        slug = (loja.id_loja_api or self._slugify(loja.nome_loja)).strip('/')
        base_url = f"https://www.mercadolivre.com.br/loja/{slug}"
        total_salvos = 0
        print(f"[ML LOJA] Coletando: {loja.nome_loja} -> {base_url}")

        for page in range(1, self.max_pages + 1):
            if total_salvos >= self.max_products_per_store:
                break

            url = base_url if page == 1 else f"{base_url}?page={page}"
            try:
                resp = self._session().get(url, timeout=20)
                if resp.status_code == 404:
                    print(f"[ML LOJA] Página não encontrada: {url}")
                    break
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, 'html.parser')
            except Exception as e:
                print(f"[ML LOJA] Erro ao abrir {url}: {e}")
                break

            product_links = self._extract_product_links_from_store(soup)
            if not product_links:
                if page == 1:
                    print(f"[ML LOJA] Nenhum produto encontrado na loja {loja.nome_loja}. Verifique o slug/HTML.")
                break

            product_links = product_links[: self.max_products_per_page]
            print(f"[ML LOJA] Página {page}: {len(product_links)} produtos (limitados)")

            for link in product_links:
                if total_salvos >= self.max_products_per_store:
                    break

                data = self._scrape_mercadolivre_product(link)
                if not data:
                    time.sleep(self.delay_sec)
                    continue

                try:
                    print(f"[ML LOJA] Processando produto: {link}") # breakpoint
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

    # --------------------- ORQUESTRAÇÃO ---------------------

    def run_collection(self):
        print("Iniciando coleta de ofertas por lojas Mercado Livre (autenticado)...")
        lojas_confiaveis = self.db_session.query(LojaConfiavel).filter_by(ativa=True).all()

        for loja in lojas_confiaveis:
            plataforma = (loja.plataforma or "").strip().lower()
            if plataforma in ("mercado livre", "mercadolivre", "ml"):
                self._scrape_ml_store(loja)
            else:
                print(f"[SKIP] Plataforma não suportada ainda: {loja.plataforma} ({loja.nome_loja})")

        print("Coleta concluída.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        collector = Collector(db)
        collector.run_collection()
    finally:
        db.close()
