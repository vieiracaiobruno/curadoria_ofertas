# -*- coding: utf-8 -*-
"""
Coletor simples baseado em requests + BeautifulSoup, agora sem hardcodes de loja
nem regras fixas de tags. O módulo percorre as LOJAS ATIVAS do banco e despacha
para o handler compatível (por plataforma/slug). Neste arquivo está implementado
apenas o coletor de "Mercado Livre Ofertas".

Mudanças principais:
- Removido self.tag_keywords e toda criação automática de Tag.
- Produtos NÃO recebem tags automaticamente; a curadoria/canais definem isso.
- Em vez de fixar "Mercado Livre Ofertas", iteramos por todas as lojas ativas e
  chamamos o handler apropriado (por plataforma/slug), evitando hardcode.
- Ajustado _has_open_offer para refletir os status atuais do pipeline.
"""
import os
import re
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional
from urllib.parse import unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

import unicodedata, re
from typing import Pattern, List
from backend.utils.config import get_config

# Imports tolerantes à estrutura do projeto
try:
    from backend.models.models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
except Exception:  # pragma: no cover
    try:
        from ..models.models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag  # type: ignore
    except Exception:  # pragma: no cover
        from models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag  # type: ignore


class SimpleCollector:
    """
    - Percorre LOJAS ATIVAS no banco e escolhe o handler por plataforma/slug.
    - Para "Mercado Livre Ofertas": visita https://www.mercadolivre.com.br/ofertas?page=N
      e extrai: nome, preços, % desconto, link e MLB code.
    - Cria/atualiza Produto, grava HistoricoPreco e cria Oferta PENDENTE_APROVACAO.
    - NÃO faz classificação por tags (isso fica com a curadoria/canais).
    """

    def __init__(self, db_session):
        self.db = db_session

        # Parâmetros de paginação
        #self.max_pages = int(os.getenv("ML_MAX_PAGES", "2"))
        #self.delay_sec = float(os.getenv("ML_REQUEST_DELAY_SEC", "0.6"))
        #self.affiliate_template = os.getenv("ML_AFFILIATE_TEMPLATE", "").strip()
        self.max_pages = int(get_config("ML_MAX_PAGES", "2"))                               # :contentReference[oaicite:13]{index=13}
        self.delay_sec = float(get_config("ML_REQUEST_DELAY_SEC", "0.6"))
        self.affiliate_template = (get_config("ML_AFFILIATE_TEMPLATE", "") or "").strip()


        # Desconto mínimo (em %)
        #min_pct = os.getenv("ML_MIN_DISCOUNT_PCT")
        #if min_pct:
        #    self.min_discount_pct = float(min_pct)
        #else:
        #    real_disc = os.getenv("REAL_DISCOUNT")  # compat: 0.10 -> 10%
        #    self.min_discount_pct = float(real_disc) * 100 if real_disc else 0.0
        min_pct = get_config("ML_MIN_DISCOUNT_PCT")
        if min_pct:
            self.min_discount_pct = float(min_pct)
        else:
            real_disc = get_config("REAL_DISCOUNT")
            self.min_discount_pct = float(real_disc) * 100 if real_disc else 0.0          # :contentReference[oaicite:14]{index=14}

        # Política de elegibilidade
        #self.require_db_tag_match = os.getenv("REQUIRE_DB_TAG_MATCH", "true").lower() in {"1","true","yes","y"}
        #self.auto_tag_on_collect  = os.getenv("AUTO_TAG_ON_COLLECT", "false").lower() in {"1","true","yes","y"}
        self.require_db_tag_match = (get_config("REQUIRE_DB_TAG_MATCH", "true") or "true").lower() in {"1","true","yes","y"}   # :contentReference[oaicite:15]{index=15}
        self.auto_tag_on_collect  = (get_config("AUTO_TAG_ON_COLLECT", "false") or "false").lower() in {"1","true","yes","y"}

        # Tags do banco como keywords
        self._tags_norm = set()               # nomes de tag normalizados
        self._tag_patterns = {}               # norm_tag -> regex compilada
        self._tags_by_norm = {}               # norm_tag -> objeto Tag
        self._load_db_tags_as_keywords()


        # Headers
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            )
        }

        # Registry de coletores por plataforma e por slug (id_loja_api)
        # Nota: mantenha os nomes de plataforma iguais aos cadastrados no banco.
        self.collectors_by_plataforma: Dict[str, Callable[[LojaConfiavel], None]] = {
            "mercado livre": self._collect_ml_ofertas_by_platform,
        }
        # Slugs específicos (id_loja_api) têm precedência sobre a plataforma
        self.collectors_by_slug: Dict[str, Callable[[LojaConfiavel], None]] = {
            "ofertas": self._collect_ml_ofertas_by_slug,
        }


    @staticmethod
    def _normalize_text(s: str) -> str:
        s = (s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))  # remove acentos
        s = re.sub(r"\s+", " ", s)
        return s

    def _compile_pattern_for_tag(self, norm_tag: str) -> Pattern:
        # curto (<=3) e alfanumérico -> exigir fronteira de palavra
        if len(norm_tag) <= 3 and re.fullmatch(r"[a-z0-9]+", norm_tag or ""):
            pat = rf"(?<!\w){re.escape(norm_tag)}(?!\w)"
        else:
            pat = re.escape(norm_tag)
        return re.compile(pat, re.IGNORECASE)

    def _load_db_tags_as_keywords(self) -> None:
        all_tags = self.db.query(Tag).all()
        self._tags_norm.clear(); self._tag_patterns.clear(); self._tags_by_norm.clear()
        for t in all_tags:
            norm = self._normalize_text(t.nome_tag)
            if not norm or norm in self._tags_norm: 
                continue
            self._tags_norm.add(norm)
            self._tag_patterns[norm] = self._compile_pattern_for_tag(norm)
            self._tags_by_norm[norm] = t

    def _match_db_tags_in_name(self, product_name: str) -> List[Tag]:
        norm_name = self._normalize_text(product_name)
        matched = []
        for norm, pat in self._tag_patterns.items():
            if pat.search(norm_name):
                matched.append(self._tags_by_norm[norm])
        return matched

    def _eligible_by_db_tags(self, product_name: str):
        """
        True se o nome do produto bater ao menos 1 tag do banco.
        Se não houver tags cadastradas:
        - retorna True se REQUIRE_DB_TAG_MATCH=false;
        - retorna False (bloqueia tudo) se REQUIRE_DB_TAG_MATCH=true (padrão).
        """
        if not self._tags_norm:
            return (not self.require_db_tag_match, [])
        matched = self._match_db_tags_in_name(product_name)
        return (len(matched) > 0, matched)


    # ----------------- utilitários -----------------

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
        # Evita duplicar quando já existe oferta "em aberto" para o mesmo produto/loja
        estados_abertos = {"PENDENTE_APROVACAO", "APROVADO", "AGENDADO", "PUBLICADO"}
        q = (
            self.db.query(Oferta)
            .filter(
                Oferta.produto_id == produto_id,
                Oferta.loja_id == loja_id,
                Oferta.status.in_(estados_abertos),
            )
            .limit(1)
            .all()
        )
        return len(q) > 0

    # Copiado/adaptado do script simples
    def _extrair_codigo(self, url: str) -> Optional[str]:
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
        except Exception:
            return 0.0

    # ----------------- persistência -----------------

    def _save_product_and_offer(self, product_data: dict, loja: LojaConfiavel) -> bool:
        """Aplica filtros, persiste Produto/Historico/Oferta.
        Elegibilidade: nome do produto deve casar com pelo menos 1 Tag do banco.
        Se não houver tags cadastradas, não bloqueia.
        """
        desconto_pct = float(product_data.get("desconto") or 0.0)
        if desconto_pct < self.min_discount_pct:
            return False

        # --------- Elegibilidade por TAGs do banco ---------
        # Import dentro do método para manter compatibilidade com sua estrutura
        try:
            from backend.models.models import Tag
        except Exception:  # pragma: no cover
            try:
                from ..models.models import Tag  # type: ignore
            except Exception:  # pragma: no cover
                from models import Tag  # type: ignore

        # Normalização simples (case/acentos)
        import unicodedata, re
        def _norm(s: str) -> str:
            s = (s or "").strip().lower()
            s = unicodedata.normalize("NFKD", s)
            s = "".join(ch for ch in s if not unicodedata.combining(ch))
            return re.sub(r"\s+", " ", s)

        def _compile_pat(token: str):
            # Tags muito curtas (<=3) e alfanuméricas exigem fronteira de palavra
            if len(token) <= 3 and re.fullmatch(r"[a-z0-9]+", token or ""):
                return re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.IGNORECASE)
            return re.compile(re.escape(token), re.IGNORECASE)

        produto_nome_norm = _norm(product_data["nome_produto"])
        tags_db = self.db.query(Tag).all()

        matched_tags = []
        if tags_db:
            for t in tags_db:
                token = _norm(t.nome_tag)
                if not token:
                    continue
                if _compile_pat(token).search(produto_nome_norm):
                    matched_tags.append(t)

            # exige ao menos 1 match quando existem tags cadastradas
            if not matched_tags:
                return False
        # ---------------------------------------------------

        # Upsert Produto por product_id_loja
        produto = (
            self.db.query(Produto)
            .filter_by(product_id_loja=product_data["product_id_loja"])
            .first()
        )
        if not produto:
            produto = Produto(
                product_id_loja=product_data["product_id_loja"],
                nome_produto=product_data["nome_produto"],
                url_base=product_data["url_base"],
                imagem_url=product_data.get("imagem_url"),
            )
            self.db.add(produto)
            self.db.flush()
        else:
            # atualização leve
            produto.nome_produto = product_data["nome_produto"] or produto.nome_produto
            if product_data.get("imagem_url"):
                produto.imagem_url = product_data["imagem_url"]

        # (Opcional) anexar as tags que deram match ao produto:
        # for t in matched_tags:
        #     if t not in produto.tags:
        #         produto.tags.append(t)

        # preço atual e último preço registrado
        last_price = self._last_price(produto.id, loja.id)
        current_price = float(product_data["preco_oferta"])
        same_price = (last_price is not None) and (abs(current_price - float(last_price)) < 1e-6)

        # Evita duplicar oferta "em aberto" para o mesmo produto/loja
        if self._has_open_offer(produto.id, loja.id):
            if not same_price:
                historico = HistoricoPreco(
                    produto_id=produto.id, loja_id=loja.id,
                    preco=current_price, data_verificacao=datetime.now()
                )
                self.db.add(historico)
                self.db.commit()
            return False

        if same_price:
            return False

        # Grava histórico do preço atual
        historico = HistoricoPreco(
            produto_id=produto.id, loja_id=loja.id,
            preco=current_price, data_verificacao=datetime.now()
        )
        self.db.add(historico)

        # Cria a oferta pendente
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


    # ----------------- scraping (ML Ofertas) -----------------

    def _fetch_ml_ofertas_page(self, page_num: int) -> str:
        url = f"https://www.mercadolivre.com.br/ofertas?page={page_num}"
        r = requests.get(url, headers=self.headers, timeout=20)
        r.raise_for_status()
        return r.text

    def _parse_ml_offers(self, html: str) -> List[dict]:
        site = BeautifulSoup(html, "html.parser")
        descricoes = site.find_all("h3", class_="poly-component__title-wrapper")
        precosAntes = site.find_all("s", class_="andes-money-amount andes-money-amount--previous andes-money-amount--cents-comma")
        precosDepois = site.find_all("span", class_="andes-money-amount andes-money-amount--cents-superscript")
        links = site.find_all("a", class_="poly-component__title")
        descontos = site.find_all("span", class_="andes-money-amount__discount")
        imagens = site.find_all("img", class_="poly-component__picture lazy-loadable")

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
                "product_id_loja": mlb,
                "nome_produto": name,
                "preco_original": price_before if price_before > 0 else None,
                "preco_oferta": price_after,
                "desconto": disc_pct,
                "url_base": href,
                "imagem_url": product_image,
                "data_validade": None,
            })
        return results

    # ----------------- handlers de coleta -----------------

    def _collect_ml_ofertas_core(self, loja: LojaConfiavel) -> int:
        """Executa a coleta do "Mercado Livre Ofertas" e persiste para a loja dada."""
        total_salvos = 0
        for page in range(1, self.max_pages + 1):
            try:
                html = self._fetch_ml_ofertas_page(page)
            except Exception as e:
                print(f"[ML OFERTAS] Falha ao acessar página {page}: {e}")
                break
            offers = self._parse_ml_offers(html)
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
        return total_salvos

    def _collect_ml_ofertas_by_platform(self, loja: LojaConfiavel) -> None:
        """
        Handler padrão para lojas com plataforma == "mercado livre".
        Se a loja tiver slug (id_loja_api) e ele for diferente de "ofertas",
        este handler pode optar por ignorar; aqui usamos a página de ofertas
        "global" do ML e associamos os resultados à loja informada.
        """
        print(f"[collector] Coletando ML Ofertas para loja '{loja.nome_loja}' (plataforma=mercado livre, slug={loja.id_loja_api})")
        self._collect_ml_ofertas_core(loja)

    def _collect_ml_ofertas_by_slug(self, loja: LojaConfiavel) -> None:
        """Handler específico quando id_loja_api == 'ofertas'."""
        print(f"[collector] Coletando ML Ofertas (slug=ofertas) para '{loja.nome_loja}'")
        self._collect_ml_ofertas_core(loja)

    # ----------------- orquestração -----------------

    def run_collection(self) -> None:
        self._load_db_tags_as_keywords()   # ← recarrega
        """
        Percorre TODAS as lojas ativas do banco e tenta coletar conforme
        plataforma/slug. Não cria tags automaticamente e não depende de
        nome de loja fixo.
        """
        lojas = (
            self.db.query(LojaConfiavel)
            .filter(LojaConfiavel.ativa == True)
            .all()
        )

        if not lojas:
            print("[collector] Não há lojas ativas cadastradas. Cadastre em Configurações > Lojas.")
            return

        handled_any = False
        for loja in lojas:
            plataforma = (loja.plataforma or "").strip().lower()
            slug = (loja.id_loja_api or "").strip().lower()

            handler = self.collectors_by_slug.get(slug) or self.collectors_by_plataforma.get(plataforma)
            if not handler:
                print(
                    f"[collector] Sem handler para loja '{loja.nome_loja}' "
                    f"(plataforma='{loja.plataforma}', slug='{loja.id_loja_api}'). Pulando."
                )
                continue

            try:
                handler(loja)
                handled_any = True
            except Exception as e:
                print(f"[collector] Erro coletando '{loja.nome_loja}': {e}")

        if not handled_any:
            print(
                "[collector] Nenhuma loja compatível encontrada. Para usar este coletor, "
                "cadastre uma loja ATIVA com plataforma='mercado livre' (e opcionalmente slug 'ofertas')."
            )
