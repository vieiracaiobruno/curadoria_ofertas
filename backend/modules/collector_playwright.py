# -*- coding: utf-8 -*-
"""
Coletor simples baseado em requests + BeautifulSoup,
derivado do comportamento de run_pipeline_simple.py, mas persistindo no banco.
"""
import os
import re
import time
from datetime import datetime
from urllib.parse import unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

# Imports tolerantes à estrutura do projeto
try:
    from backend.models.models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
except Exception:
    try:
        from ..models.models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag  # type: ignore
    except Exception:
        from models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag  # type: ignore

class SimpleCollector:
    """
    - Percorre páginas de https://www.mercadolivre.com.br/ofertas?page=N
    - Extrai: nome, preço anterior, preço atual, % desconto (se houver), link e MLB code
    - Cria/atualiza Produto, grava HistoricoPreco e cria Oferta pendente de aprovação
    - Usa regras de tags e filtros simples por palavras-chave
    """

    def __init__(self, db_session):
        self.db = db_session

        # Parâmetros de paginação
        self.max_pages = int(os.getenv("ML_MAX_PAGES", "2"))
        self.delay_sec = float(os.getenv("ML_REQUEST_DELAY_SEC", "0.6"))
        self.affiliate_template = os.getenv("ML_AFFILIATE_TEMPLATE", "").strip()

        # Desconto mínimo (em %)
        min_pct = os.getenv("ML_MIN_DISCOUNT_PCT")
        if min_pct:
            self.min_discount_pct = float(min_pct)
        else:
            # compatibilidade com REAL_DISCOUNT (ex: 0.10 -> 10%)
            real_disc = os.getenv("REAL_DISCOUNT")
            self.min_discount_pct = float(real_disc) * 100 if real_disc else 0.0

        # Filtros simples (palavras-chave)
        def _parse_csv_env(name: str):
            raw = os.getenv(name, "").strip()
            if not raw:
                return set()
            return {x.strip().lower() for x in raw.split(",") if x.strip()}

        self.allow_kw = _parse_csv_env("ML_ALLOW_KEYWORDS")
        self.block_kw = _parse_csv_env("ML_BLOCK_KEYWORDS")

        # Headers
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            )
        }

        # Palavras-chave -> tags
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

    # ----------------- utilitários -----------------

    def _affiliate_url(self, raw_url: str) -> str:
        if self.affiliate_template:
            try:
                from urllib.parse import quote
                return self.affiliate_template.format(url=quote(raw_url, safe=""))
            except Exception:
                return raw_url
        return raw_url

    def _suggest_tags(self, product_name):
        suggested_tags = []
        name_lower = product_name.lower()
        for tag_name, keywords in self.tag_keywords.items():
            if any(keyword in name_lower for keyword in keywords):
                tag = self.db.query(Tag).filter_by(nome_tag=tag_name).first()
                if not tag:
                    tag = Tag(nome_tag=tag_name)
                    self.db.add(tag)
                    self.db.commit()
                    self.db.refresh(tag)
                suggested_tags.append(tag)
        return suggested_tags

    def _passes_keyword_filters(self, product_name: str) -> bool:
        name = product_name.lower()
        if self.allow_kw and not any(kw in name for kw in self.allow_kw):
            return False
        if self.block_kw and any(kw in name for kw in self.block_kw):
            return False
        return True

    def _last_price(self, produto_id: int, loja_id: int):
        last = (
            self.db.query(HistoricoPreco)
            .filter(HistoricoPreco.produto_id == produto_id, HistoricoPreco.loja_id == loja_id)
            .order_by(HistoricoPreco.data_verificacao.desc())
            .first()
        )
        return last.preco if last else None

    def _has_open_offer(self, produto_id: int, loja_id: int) -> bool:
        from backend.models.models import Oferta  # import local para evitar ciclo
        q = (
            self.db.query(Oferta)
            .filter(Oferta.produto_id == produto_id, Oferta.loja_id == loja_id, Oferta.status.in_({"PENDENTE_APROVACAO","APROVADA_PARA_CURADORIA","AGENDADO","PUBLICADO"}))
            .limit(1)
            .all()
        )
        return len(q) > 0

    def _ensure_ml_ofertas_store(self) -> LojaConfiavel: 
        loja = self.db.query(LojaConfiavel).filter_by(nome_loja="Mercado Livre Ofertas").first()
        print(f"Debug: Loja encontrada: {loja}")
        if not loja:
            loja = LojaConfiavel(
                nome_loja="Mercado Livre Ofertas",
                plataforma="mercado livre",
                id_loja_api=None,
                pontuacao_confianca=5,
                ativa=True
            )
            self.db.add(loja)
            self.db.commit()
            self.db.refresh(loja)
        return loja

    # Copiado/adaptado do script simples
    def _extrair_codigo(self, url: str):
        if not url:
            return None
        padroes = [r"MLB-\d{10}", r"MLB\d{8,}"]
        if "click1.mercadolivre.com.br" in url:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            destino = qs.get("url", [None])[0]
            if destino:
                url_produto = unquote(destino)
                for p in padroes:
                    m = re.search(p, url_produto)
                    if m:
                        return m.group()
        for p in padroes:
            m = re.search(p, url)
            if m:
                return m.group()
        return None

    def _parse_price_brl(self, txt: str) -> float:
        if not txt:
            return 0.0
        txt = txt.strip()
        txt = re.sub(r"[^\d,\.]", "", txt)
        txt = txt.replace(".", "").replace(",", ".")
        try:
            return float(txt)
        except:
            return 0.0

    # ----------------- persistência -----------------

    def _save_product_and_offer(self, product_data, loja: LojaConfiavel):
        from backend.models.models import Oferta, Produto, HistoricoPreco  # evitar conflito circular
        desconto_pct = product_data.get("desconto") or 0.0
        print(f"Debug: Produto {product_data.get('nome_produto')} com desconto {desconto_pct}%")
        print(f"Debug: min_discount_pct={self.min_discount_pct}")
        if desconto_pct < self.min_discount_pct:
            return False
        print("Debug: passou filtro de desconto")

        if not self._passes_keyword_filters(product_data["nome_produto"]):
            return False
        print("Debug: passou filtro de palavras-chave")

        produto = self.db.query(Produto).filter_by(product_id_loja=product_data["product_id_loja"]).first()
        print(f"Debug: Produto no banco: {produto}")
        if not produto:
            produto = Produto(
                product_id_loja=product_data["product_id_loja"],
                nome_produto=product_data["nome_produto"],
                url_base=product_data["url_base"],
                imagem_url=product_data.get("imagem_url"),
            )
            self.db.add(produto)
            self.db.flush()

            suggested = self._suggest_tags(product_data["nome_produto"])
            for tag in suggested:
                produto.tags.append(tag)
            self.db.commit()
            self.db.refresh(produto)
        else:
            # atualização leve
            produto.nome_produto = product_data["nome_produto"] or produto.nome_produto
            if product_data.get("imagem_url"):
                produto.imagem_url = product_data["imagem_url"]
            suggested = self._suggest_tags(product_data["nome_produto"])
            for tag in suggested:
                if tag not in produto.tags:
                    produto.tags.append(tag)
            self.db.commit()
            self.db.refresh(produto)

        # preço mudou?
        last_price = self._last_price(produto.id, loja.id)
        current_price = float(product_data["preco_oferta"])
        same_price = (last_price is not None) and (abs(current_price - float(last_price)) < 1e-6)

        if self._has_open_offer(produto.id, loja.id):
            if not same_price:
                historico = HistoricoPreco(
                    produto_id=produto.id, loja_id=loja.id, preco=current_price, data_verificacao=datetime.now()
                )
                self.db.add(historico)
                self.db.commit()
            return False

        if same_price:
            return False

        historico = HistoricoPreco(
            produto_id=produto.id, loja_id=loja.id, preco=current_price, data_verificacao=datetime.now()
        )
        self.db.add(historico)

        oferta = Oferta(
            produto_id=produto.id,
            loja_id=loja.id,
            preco_original=product_data.get("preco_original"),
            preco_oferta=current_price,
            url_afiliado_longa=self._affiliate_url(product_data["url_base"]),
            data_encontrado=datetime.now(),
            data_validade=product_data.get("data_validade"),
            status="PENDENTE_APROVACAO",
        )
        self.db.add(oferta)
        self.db.commit()
        return True

    # ----------------- scraping -----------------

    def _fetch_page(self, page_num: int):
        url = f"https://www.mercadolivre.com.br/ofertas?page={page_num}"
        r = requests.get(url, headers=self.headers, timeout=20)
        r.raise_for_status()
        return r.text

    def _parse_offers(self, html: str):
        site = BeautifulSoup(html, "html.parser")
        descricoes = site.find_all("h3", class_="poly-component__title-wrapper")
        precosAntes = site.find_all("s", class_="andes-money-amount andes-money-amount--previous andes-money-amount--cents-comma")
        precosDepois = site.find_all("span", class_="andes-money-amount andes-money-amount--cents-superscript")
        links = site.find_all("a", class_="poly-component__title")
        descontos = site.find_all("span", class_="andes-money-amount__discount")

        results = []
        for descricao, precoAntes, precoDepois, link, desconto in zip(descricoes, precosAntes, precosDepois, links, descontos):
            href = link.get("href", "") or ""
            name = (descricao.get_text(strip=True) or "").strip()
            price_before = self._parse_price_brl(precoAntes.get_text(strip=True) if precoAntes else "")
            price_after = self._parse_price_brl(precoDepois.get_text(strip=True) if precoDepois else "")
            disc_txt = (desconto.get_text(strip=True) if desconto else "").replace("%", "").replace("OFF", "")
            try:
                disc_pct = float(re.sub(r"[^0-9,\.]", "", disc_txt).replace(",", "."))
            except:
                disc_pct = 0.0
            mlb = self._extrair_codigo(href) or "N/A"

            results.append({
                "product_id_loja": mlb,
                "nome_produto": name,
                "preco_original": price_before if price_before > 0 else None,
                "preco_oferta": price_after,
                "desconto": disc_pct,
                "url_base": href,
                "imagem_url": None,
                "data_validade": None,
            })
        return results

    def run_collection(self):
        loja = self._ensure_ml_ofertas_store()
        total_salvos = 0
        for page in range(1, self.max_pages + 1):
            try:
                html = self._fetch_page(page)
            except Exception as e:
                print(f"[ML OFERTAS] Falha ao acessar página {page}: {e}")
                break
            offers = self._parse_offers(html)
            if not offers:
                print("[ML OFERTAS] Nenhuma oferta encontrada nesta página.")
                break
            for o in offers:
                try:
                    if self._save_product_and_offer(o, loja):
                        total_salvos += 1
                        print(f"[ML OFERTAS] Salvo: {o['nome_produto'][:80]}... ({o['desconto']:.1f}% off)")
                    else:
                        print(f"[ML OFERTAS] Ignorado: {o['nome_produto'][:80]}")
                except Exception as e:
                    print(f"[ML OFERTAS] Erro ao salvar oferta: {e}")
                time.sleep(self.delay_sec)
        print(f"[ML OFERTAS] Concluído. Ofertas salvas: {total_salvos}")
