# -*- coding: utf-8 -*-
"""
Collector Mercado Livre:
- SEMPRE faz scraping global das páginas de ofertas (ignora lojas cadastradas para buscar).
- Salva/atualiza TODOS os Produtos SEM filtro.
- Cria Oferta somente se:
    * Loja (seller) já existir na tabela lojas_confiaveis (NÃO cria loja aqui)
    * Passar filtro de tags (se houver tags e REQUIRE_DB_TAG_MATCH=true)
    * Não existir oferta aberta mesma loja/produto/preço.
"""
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
import unicodedata
from sqlalchemy.exc import IntegrityError

from backend.utils.config import get_config

try:
    from backend.models.models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
except Exception:  # pragma: no cover
    from ..models.models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag  # type: ignore


class Collector:
    def __init__(self, db_session):
        self.db = db_session
        self.max_pages = int(get_config("ML_MAX_PAGES", "2"))
        self.delay_sec = float(get_config("ML_REQUEST_DELAY_SEC", "0.6"))
        self.affiliate_template = (get_config("ML_AFFILIATE_TEMPLATE", "") or "").strip()

        min_pct = get_config("ML_MIN_DISCOUNT_PCT")
        if min_pct:
            self.min_discount_pct = float(min_pct)
        else:
            real_disc = get_config("REAL_DISCOUNT")
            self.min_discount_pct = float(real_disc) * 100 if real_disc else 0.0

        self.require_db_tag_match = (get_config("REQUIRE_DB_TAG_MATCH", "true") or "true").lower() in {"1", "true", "yes", "y"}
        self.auto_tag_on_collect = (get_config("AUTO_TAG_ON_COLLECT", "false") or "false").lower() in {"1", "true", "yes", "y"}

        self._tags_norm = set()
        self._tag_patterns: Dict[str, re.Pattern] = {}
        self._tags_by_norm: Dict[str, Tag] = {}
        self._load_db_tags_as_keywords()

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            )
        }

    # ---------------- Tags ----------------
    @staticmethod
    def _normalize_text(s: str) -> str:
        s = (s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", s)

    def _compile_pattern_for_tag(self, norm_tag: str) -> re.Pattern:
        if len(norm_tag) <= 3 and re.fullmatch(r"[a-z0-9]+", norm_tag):
            pat = rf"(?<!\w){re.escape(norm_tag)}(?!\w)"
        else:
            pat = re.escape(norm_tag)
        return re.compile(pat, re.IGNORECASE)

    def _load_db_tags_as_keywords(self):
        tags = self.db.query(Tag).all()
        self._tags_norm.clear(); self._tag_patterns.clear(); self._tags_by_norm.clear()
        for t in tags:
            norm = self._normalize_text(t.nome_tag)
            if not norm or norm in self._tags_norm:
                continue
            self._tags_norm.add(norm)
            self._tag_patterns[norm] = self._compile_pattern_for_tag(norm)
            self._tags_by_norm[norm] = t

    def _match_db_tags_in_name(self, product_name: str) -> List[Tag]:
        norm_name = self._normalize_text(product_name)
        return [self._tags_by_norm[n] for n, pat in self._tag_patterns.items() if pat.search(norm_name)]

    def _eligible_by_db_tags(self, product_name: str):
        if not self._tags_norm:
            return (not self.require_db_tag_match, [])
        matched = self._match_db_tags_in_name(product_name)
        return (len(matched) > 0, matched)

    # --------------- Utils ---------------
    def _affiliate_url(self, raw_url: str) -> str:
        if self.affiliate_template:
            try:
                from urllib.parse import quote
                return self.affiliate_template.format(url=quote(raw_url, safe=""))
            except Exception:
                return raw_url
        return raw_url

    def _last_price(self, produto_id: int, loja_id: int) -> Optional[float]:
        last = (
            self.db.query(HistoricoPreco)
            .filter(HistoricoPreco.produto_id == produto_id, HistoricoPreco.loja_id == loja_id)
            .order_by(HistoricoPreco.data_verificacao.desc())
            .first()
        )
        return float(last.preco) if last else None

    def _has_open_offer(self, produto_id: int, loja_id: int) -> bool:
        estados_abertos = {"PENDENTE_APROVACAO", "APROVADO", "AGENDADO", "PUBLICADO"}
        return self.db.query(Oferta).filter(
            Oferta.produto_id == produto_id,
            Oferta.loja_id == loja_id,
            Oferta.status.in_(estados_abertos)
        ).first() is not None

    def _extrair_codigo(self, url: str) -> Optional[str]:
        if not url:
            return None
        padroes = [r"MLB-\d{10}", r"MLB\d{8,}"]
        if "click1.mercadolivre.com.br" in url:
            parsed = urlparse(url)
            destino = parse_qs(parsed.query).get("url", [None])[0]
            if destino:
                destino_dec = unquote(destino)
                for p in padroes:
                    m = re.search(p, destino_dec)
                    if m:
                        return m.group()
        for p in padroes:
            m = re.search(p, url)
            if m:
                codigo = m.group()
                return codigo.replace("MLB-", "MLB")  # remove o hífen se existir
        return None

    def _parse_price_brl(self, txt: str) -> float:
        if not txt:
            return 0.0
        txt = re.sub(r"[^\d,\.]", "", txt.strip()).replace(".", "").replace(",", ".")
        try:
            return float(txt)
        except Exception:
            return 0.0

    # --------------- Store resolution (somente para oferta) ---------------
    def _resolve_store_from_product_page(self, product_url: str) -> Dict[str, Optional[str]]:
        """
        Baixa a página do produto e extrai:
          seller_id        -> id_loja_api (seller_id ou official_store_id)
          item_id_alt      -> id_loja_api_alt (item_id)
          store_name       -> nome da loja (sem 'Vendido por')
          id_product       -> código principal do produto (parent_url -> /p/MLBxxxx)
        """
        out = {"seller_id": None, "item_id_alt": None, "store_name": None, "id_product": None}
        if not product_url:
            return out
        try:
            #print("Resolvendo loja na página do produto:", product_url)          
            time.sleep(self.delay_sec)
            r = requests.get(product_url, headers=self.headers, timeout=10)  
            if not r.ok:
                return out
            soup = BeautifulSoup(r.text, "html.parser")

            # --- seller / item alt (link com parâmetros) ---
            link = soup.select_one("a.andes-button.andes-button--medium.andes-button--quiet.andes-button--full-width[href]")
            if not link:
                #print("Link principal não encontrado, tentando alternativo...")
                link = soup.select_one('a[href*="item_id="][href*="seller_id="]') or \
                       soup.select_one('a[href*="item_id="][href*="official_store_id="]')
            if link:
                #print("Link encontrado:", link.get("href"))
                q = parse_qs(urlparse(link.get("href")).query)
                out["item_id_alt"] = (q.get("item_id", [None])[0] or "").strip() or None
                #print("item_id_alt extraído:", out["item_id_alt"])
                out["seller_id"] = (
                    (q.get("seller_id", [None])[0] or "").strip()
                    or (q.get("official_store_id", [None])[0] or "").strip()
                    or None
                )
                #print("seller_id extraído:", out["seller_id"])

            # --- nome da loja ---
            h2 = soup.select_one("h2.ui-seller-data-header__title") or soup.select_one(
                "h2.ui-pdp-color--BLACK.ui-pdp-size--MEDIUM.ui-pdp-family--SEMIBOLD.ui-seller-data-header__title.non-selectable"
            )
            if h2:
                name = h2.get_text(strip=True)
                if name.lower().startswith("vendido por"):
                    name = name[len("vendido por"):].strip()
                out["store_name"] = name

            # --- id_product (parent_url hidden input) ---
            parent_input = soup.find("input", {"type": "hidden", "name": "parent_url"})
            if parent_input:
                val = parent_input.get("value") or ""
                # Suporta dois formatos:
                # 1) /p/MLB47519001
                # 2) https://produto.mercadolivre.com.br/MLB-5421177204-conjunto-...
                def _extract_id_product(parent_val: str) -> Optional[str]:
                    if not parent_val:
                        return None
                    # Formato /p/MLBxxxxx
                    m = re.search(r"/p/(MLB\d+)", parent_val, re.IGNORECASE)
                    if m:
                        return m.group(1).upper()
                    # Formato URL ou slug com MLB-########## (listing) -> normaliza removendo hífen
                    m = re.search(r"(MLB-\d+)", parent_val, re.IGNORECASE)
                    if m:
                        return m.group(1).upper().replace("MLB-", "MLB")
                    # Fallback: qualquer MLB#########
                    m = re.search(r"(MLB\d+)", parent_val, re.IGNORECASE)
                    if m:
                        return m.group(1).upper()
                    return None

                extracted = _extract_id_product(val)
                if extracted:
                    out["id_product"] = extracted

        except Exception:
            pass
        return out

    def _find_existing_store(self, seller_id: Optional[str], alt_id: Optional[str]) -> Optional[LojaConfiavel]:
        q = self.db.query(LojaConfiavel)
        conds = []
        if seller_id:
            conds.append(LojaConfiavel.id_loja_api == seller_id)
        if alt_id:
            conds.append(LojaConfiavel.id_loja_api_alt == alt_id)
        #if store_name:
        #    conds.append(LojaConfiavel.nome_loja == store_name)
        if not conds:
            return None
        from sqlalchemy import or_
        return q.filter(or_(*conds)).first()

    def _find_existing_store_by_altid(self, alt_id: Optional[str]) -> Optional[LojaConfiavel]:
        q = self.db.query(LojaConfiavel)
        conds = []
        if alt_id:
            conds.append(LojaConfiavel.id_loja_api_alt == alt_id)
        if not conds:
            return None
        from sqlalchemy import or_
        return q.filter(or_(*conds)).first()

    # --------------- Persistência ---------------
    def _save_product_and_offer(self, product_data: dict):
        """
        Salva/atualiza sempre o Produto.
        (Reincluída) lógica de criação automática da loja em LojaConfiavel caso não exista
        (cria com ativa=False para precisar de ativação posterior).
        Identificação do produto prioriza:
          1. id_product extraído (se a coluna existir)
          2. product_id_loja_alt
          3. product_id_loja
        Cria Oferta somente se a loja existir e estiver ativa e passar filtro de tags.
        """
        from sqlalchemy import or_

        # Extrai dados completos da página (ids de loja / id_product / nome loja)
        store_info = self._resolve_store_from_product_page(product_data["url_base"])
        #print("Url do produto:", product_data["url_base"])
        print(f"[collector] Extraídos - seller_id: {store_info.get('seller_id')}, item_id_alt: {store_info.get('item_id_alt')}, store_name: {store_info.get('store_name')}, id_product: {store_info.get('id_product')}")
        id_product_store = store_info.get("id_product") or None
        alt_code = (store_info.get("item_id_alt") or "").strip() or None
        listing_code = (store_info.get("seller_id") or "").strip() or None

        # Normalização MLB-
        def _norm(c: Optional[str]):
            return c.replace("MLB-", "MLB") if c and "MLB-" in c else c

        id_product_store = _norm(id_product_store)
        alt_code = _norm(alt_code)
        listing_code = _norm(listing_code)

        # Assegura ao menos um código para salvar
        if not listing_code:
            listing_code = alt_code or id_product_store or "AUTO_GEN"

        # Localiza produto existente
        #produto = None
        #if id_product_store and hasattr(Produto, "id_product"):
        #    produto = self.db.query(Produto).filter(Produto.id_product == id_product_store).first()

        #if not produto and alt_code:
        #    produto = self.db.query(Produto).filter(
        #        or_(Produto.product_id_loja_alt == alt_code,
        #            Produto.product_id_loja == alt_code)
        #    ).first()

        #if not produto:
        #    produto = self.db.query(Produto).filter(Produto.product_id_loja == listing_code).first()

        # Localiza loja existente
        loja = self._find_existing_store(store_info.get("seller_id"), store_info.get("item_id_alt"))

        # Cria loja automaticamente se não existir e houver identificadores mínimos
        if not loja:
            seller_id = (store_info.get("seller_id") or "").strip() or None
            alt_id = (store_info.get("item_id_alt") or "").strip() or None
            nome_loja = (store_info.get("store_name") or "").strip()
            if seller_id or alt_id:
                if not nome_loja:
                    nome_loja = f"Loja {seller_id or alt_id}"
                try:
                    nova_loja = LojaConfiavel(
                        nome_loja=nome_loja,
                        plataforma="Mercado Livre",
                        id_loja_api=seller_id,
                        id_loja_api_alt=alt_id,
                        pontuacao_confianca=3,
                        ativa=False,  # permanece inativa até ativação manual
                        **({"lojaconfiavel": True} if hasattr(LojaConfiavel, "lojaconfiavel") else {})
                    )
                    self.db.add(nova_loja)
                    self.db.commit()
                    loja = nova_loja
                except IntegrityError:
                    self.db.rollback()
                    loja = self._find_existing_store(seller_id, alt_id)
                except Exception:
                    self.db.rollback()

        # Localiza produto existente
        produto = None
        if id_product_store and hasattr(Produto, "id_product"):
            produto = self.db.query(Produto).filter(Produto.id_product == id_product_store).first()

        # Cria / atualiza produto
        if not produto:
            fields = {
                "id_product": id_product_store,
                "product_id_loja": listing_code,
                "product_id_loja_alt": alt_code,
                "nome_produto": product_data["nome_produto"],
                "url_base": product_data["url_base"],
                "imagem_url": product_data.get("imagem_url"),
            }
            if hasattr(Produto, "id_product"):
                fields["id_product"] = id_product_store or alt_code or listing_code
            #print(f"[collector] Criando produto: {fields['id_product']}")
            produto = Produto(**fields)
            self.db.add(produto)
            self.db.flush()
        else:
            if product_data.get("nome_produto"):
                produto.nome_produto = product_data["nome_produto"]
            if product_data.get("imagem_url"):
                produto.imagem_url = product_data["imagem_url"]
            if hasattr(produto, "id_product") and not getattr(produto, "id_product") and id_product_store:
                produto.id_product = id_product_store
            if not produto.product_id_loja_alt and alt_code:
                produto.product_id_loja_alt = alt_code

        # Tags automáticas
        if self.auto_tag_on_collect:
            for tag in self._match_db_tags_in_name(product_data["nome_produto"]):
                if tag not in produto.tags:
                    produto.tags.append(tag)

        self.db.commit()
        self.db.refresh(produto)

        # Rebusca loja via alt_id se ainda não resolvida
        if not loja and alt_code:
            loja = self._find_existing_store_by_altid(alt_code)

        # Só cria oferta se loja ativa
        if not loja or not loja.ativa:
            return False

        eligible, _matched = self._eligible_by_db_tags(product_data["nome_produto"])
        if not eligible:
            return False

        current_price = float(product_data.get("preco_oferta") or 0.0)
        last_price = self._last_price(produto.id, loja.id)
        same_price = last_price is not None and abs(current_price - last_price) < 1e-6

        if self._has_open_offer(produto.id, loja.id):
            if not same_price:
                self.db.add(HistoricoPreco(
                    produto_id=produto.id,
                    loja_id=loja.id,
                    preco=current_price,
                    data_verificacao=datetime.utcnow()
                ))
                self.db.commit()
            return False
        if same_price:
            return False

        self.db.add(HistoricoPreco(
            produto_id=produto.id,
            loja_id=loja.id,
            preco=current_price,
            data_verificacao=datetime.utcnow()
        ))

        oferta = Oferta(
            produto_id=produto.id,
            loja_id=loja.id,
            preco_original=product_data.get("preco_original"),
            preco_oferta=current_price,
            status="PENDENTE_APROVACAO",
            url_afiliado_longa=self._affiliate_url(product_data["url_base"]) if hasattr(Oferta, "url_afiliado_longa") else None,
        )
        if hasattr(oferta, "data_encontrado"):
            oferta.data_encontrado = datetime.utcnow()
        if hasattr(oferta, "data_validade") and product_data.get("data_validade"):
            oferta.data_validade = product_data["data_validade"]

        self.db.add(oferta)
        self.db.commit()
        return True

    # --------------- Scraping ---------------
    def _fetch_ml_ofertas_page(self, page_num: int) -> str:
        url = f"https://www.mercadolivre.com.br/ofertas?page={page_num}"
        r = requests.get(url, headers=self.headers, timeout=10)
        r.raise_for_status()
        print(f"[collector] Página {page_num} OK")
        return r.text

    def _parse_ml_offers(self, html: str) -> List[dict]:
        site = BeautifulSoup(html, "html.parser")
        descricoes = site.find_all("h3", class_="poly-component__title-wrapper")
        precosAntes = site.find_all("s", class_="andes-money-amount andes-money-amount--previous andes-money-amount--cents-comma")
        precosDepois = site.find_all("span", class_="andes-money-amount andes-money-amount--cents-superscript")
        links = site.find_all("a", class_="poly-component__title")
        descontos = site.find_all("span", class_="andes-money-amount__discount")
        imagens = site.find_all("img", class_="poly-component__picture")

        results: List[dict] = []
        for descricao, precoAntes, precoDepois, link, desconto, imagem in zip(descricoes, precosAntes, precosDepois, links, descontos, imagens):
            href = link.get("href", "") or ""
            name = (descricao.get_text(strip=True) or "").strip()
            price_before = self._parse_price_brl(precoAntes.get_text(strip=True) if precoAntes else "")
            price_after = self._parse_price_brl(precoDepois.get_text(strip=True) if precoDepois else "")
            disc_txt = (desconto.get_text(strip=True) if desconto else "").replace("%", "").replace("OFF", "")
            product_image = imagem.get("data-src", "") or ""
            try:
                disc_pct = float(re.sub(r"[^0-9,\.]", "", disc_txt).replace(",", "."))
            except Exception:
                disc_pct = 0.0
            mlb = self._extrair_codigo(href) or "N/A"
            results.append({
                #"id_product": None,
                "product_id_loja": None,
                "product_id_loja_alt": mlb,
                "nome_produto": name,
                "preco_original": price_before if price_before > 0 else None,
                "preco_oferta": price_after,
                "desconto": disc_pct,
                "url_base": href,
                "imagem_url": product_image,
                "data_validade": None,
            })
        return results

    # --------------- Execução Global ---------------
    def run_collection(self):
        print("[collector] Iniciando coleta global de ofertas do Mercado Livre...")
        all_offers: List[dict] = []
        for page in range(1, self.max_pages + 1):
            try:
                html = self._fetch_ml_ofertas_page(page)
                offers = self._parse_ml_offers(html)
                if not offers:
                    print("[collector] Sem resultados adicionais.")
                    break
                all_offers.extend(offers)
                time.sleep(self.delay_sec)
            except Exception as e:
                print(f"[collector] Erro página {page}: {e}")
                break

        created_offers = 0
        for o in all_offers:
            try:
                if self._save_product_and_offer(o):
                    created_offers += 1
            except Exception as e:
                print(f"[collector] Erro ao processar item: {e}")

        print(f"[collector] Coleta concluída. Produtos processados: {len(all_offers)} | Ofertas criadas: {created_offers}")
        return created_offers
