from __future__ import annotations

import json
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup

from backend.models.models import LinkColeta
from backend.modules.utils.selenium_client import SeleniumClient
from backend.modules.utils.config import get_config


class MLParser:
    """
    Parser específico para Mercado Livre.
    Extrai informações completas de um link de produto ML.
    """

    def __init__(self, selenium_client: Optional[SeleniumClient] = None):
        self.delay_sec = float(get_config("ML_REQUEST_DELAY_SEC", "2"))
        self.client = selenium_client

    def parse(self, link: LinkColeta, client: SeleniumClient) -> Optional[Dict]:
        """
        Parseia um link do Mercado Livre e retorna os dados extraídos.
        
        Args:
            link: Objeto LinkColeta da tabela
            client: SeleniumClient para fazer requisições
        
        Returns:
            Dict com dados parseados ou None se falhar
        """
        url = link.url
        if not url:
            return None

        try:
            # Busca a página do produto
            html = client.get_page(
                url,
                wait_any_id=["__PRELOADED_STATE__"],
                timeout_sec=self.delay_sec,
            )
            soup = BeautifulSoup(html, "html.parser")
            data = self._extract__preloaded_json(soup)

            # Extrai informações
            result = {
                "source": "mercadolivre",
                "url_base": url,
                "store_name": self._extract_store_name(data),
                "seller_id": self._extract_seller_id(data),
                "id_product": self._extract_id_product(data),
                "preco_original": self._extract_price_before(data),
                "preco_oferta": self._extract_price_after(data),
                "desconto": self._extract_discount(data),
                "nome_produto": self._extract_product_name(data),
                "imagem_url": self._extract_product_image(data),
                "seller_score": self._extract_seller_score(soup),
                "ganho_real": self._extract_ganho_real(soup),
                "url_afiliado_curta": client.get_short_affiliate_url(soup, delay=self.delay_sec) or None
            }

            # Valida que campos essenciais foram extraídos
            required = ["id_product", "seller_id", "nome_produto", "preco_oferta"]
            if all(result.get(f) for f in required):
                return result
            else:
                print(f"[MLParser] Campos essenciais faltando em {url}")
                return None

        except Exception as e:
            print(f"[MLParser] Erro ao parsear {url}: {e}")
            return None

    def _extract__preloaded_json(self, soup: BeautifulSoup) -> Optional[dict]:
        tag = soup.find("script", id="__PRELOADED_STATE__", attrs={"type": "application/json"})
        if not tag:
            return None
        raw = tag.string or ""
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except Exception:
            try:
                return json.loads(raw.encode("utf-8").decode("unicode_escape"))
            except Exception:
                return None

    def _extract_seller_id(self, data: Optional[dict]) -> Optional[str]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            if isinstance(node, dict):
                node = node.get("track", {})
                node = node.get("melidata_event", {})
                node = node.get("event_data", {})
                id = node.get("seller_id") or node.get("seller-id")
                if isinstance(id, int):
                    return str(id)
                if isinstance(id, str):
                    sid = id.strip()
                    if sid.isdigit():
                        return sid
        except Exception:
            pass
        return None

    def _extract_id_product(self, data: Optional[dict]) -> Optional[str]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            id = node.get("id")
            if isinstance(id, str) and id.strip():
                return id.strip()
        except Exception:
            pass
        return None

    def _extract_store_name(self, data: Optional[dict]) -> Optional[str]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            if isinstance(node, dict):
                node = node.get("track", {})
                node = node.get("melidata_event", {})
                node = node.get("event_data", {})
                name = node.get("seller_name") or node.get("seller-name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
                else:
                    node = data.get("pageState", {})
                    node = node.get("initialState", {})
                    node = node.get("components", {})
                    if isinstance(node, dict):
                        node = node.get("available_quantity", {})
                        node = node.get("picker", {})
                        node = node.get("track", {})
                        node = node.get("melidata_event", {})
                        node = node.get("event_data", {})
                        name = node.get("seller_name") or node.get("seller-name")
                        if isinstance(name, str) and name.strip():
                            return name.strip()
        except Exception:
            pass
        return None

    def _extract_price_before(self, data: Optional[dict]) -> Optional[float]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            if isinstance(node, dict):
                node = node.get("price", {})
                node = node.get("price", {})
                value = node.get("original_value") or node.get("original-value")
                if isinstance(value, (int, float)):
                    return float(value)
        except Exception:
            pass
        return None

    def _extract_price_after(self, data: Optional[dict]) -> Optional[float]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            if isinstance(node, dict):
                node = node.get("price", {})
                node = node.get("price", {})
                value = node.get("value")
                if isinstance(value, (int, float)):
                    return float(value)
        except Exception:
            pass
        return None

    def _extract_discount(self, data: Optional[dict]) -> Optional[float]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            if isinstance(node, dict):
                node = node.get("price", {})
                node = node.get("discount_label", {}) or node.get("discount-label", {})
                value = node.get("value")
                if isinstance(value, (int, float)):
                    return float(value)
        except Exception:
            pass
        return None

    def _extract_product_name(self, data: Optional[dict]) -> Optional[str]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            if isinstance(node, dict):
                node = node.get("share", {})
                name = node.get("title")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        except Exception:
            pass
        return None

    def _extract_product_image(self, data: Optional[dict]) -> Optional[str]:
        if not data or not isinstance(data, dict):
            return None
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            if isinstance(node, dict):
                node = node.get("share", {})
                node = node.get("picture", {})
                id = node.get("id")
                if isinstance(id, str) and id.strip():
                    return "https://http2.mlstatic.com/D_NQ_NP_" + id.strip() + "-O.webp"
        except Exception:
            pass
        return None

    def _extract_seller_score(self, soup: BeautifulSoup) -> Optional[int]:
        candidates = soup.find_all("ul")
        best = None
        for ul in candidates:
            cls = ul.get("class") or []
            cls_set = set(cls)
            if "ui-seller-data-status__thermometer" in cls_set and "thermometer-large" in cls_set:
                best = ul
                break
            if "ui-seller-data-status__thermometer" in cls_set and best is None:
                best = ul
            if any("thermometer" in c for c in cls_set) and best is None:
                best = ul
        if not best:
            return None
        raw_val = best.get("value") or best.get("data-value") or ""
        try:
            return int(raw_val)
        except Exception:
            return None

    def _extract_ganho_real(self, soup: BeautifulSoup) -> Optional[float]:
        if not soup:
            return None
        # Primeira tentativa: busca por span com texto "GANHO"
        try:
            spans = soup.find_all("span")
            for sp in spans:
                txt = (sp.get_text(strip=True) or "").upper()
                if "GANHO" not in txt:
                    continue
                cls = " ".join(sp.get("class") or [])
                if "andes-typography" not in cls:
                    continue
                m = re.search(r"GANHOS?\s+(\d+(?:[.,]\d+)?)\s*%", txt, re.IGNORECASE) or \
                    re.search(r"(\d+(?:[.,]\d+)?)\s*%", txt)
                if m:
                    val = m.group(1).replace(",", ".")
                    try:
                        pct = float(val)
                        if 0 <= pct <= 1000:
                            return round(pct, 2)
                    except Exception:
                        continue
        except Exception:
            pass
        # Segunda tentativa: busca na estrutura stripe-commission__percentage
        try:
            perc_span = soup.find("span", class_="stripe-commission__percentage")
            if perc_span:
                val = perc_span.get_text(strip=True).replace("%", "").replace(",", ".")
                try:
                    pct = float(val)
                    if 0 <= pct <= 1000:
                        return round(pct, 2)
                except Exception:
                    pass
        except Exception:
            pass
        return None
