from __future__ import annotations

from os import name
import re
import json
import time
import random
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests
# Selenium (para clicar no botão Compartilhar)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    from .base import BaseCollector
except Exception:
    from backend.modules.collectors.base import BaseCollector
try:
    from ..utils.config import get_config
    from ..utils.selenium_client import SeleniumClient
except Exception:
    from backend.modules.utils.config import get_config
    from backend.modules.utils.selenium_client import SeleniumClient


class MLCollector(BaseCollector):
    """
    Extração de ofertas do Mercado Livre.
    - Navega nas páginas de ofertas
    - Extrai dados de listagem
    - Abre página do produto para enriquecer (seller, MLB, score, ganho_real, short_link)
    NÃO grava no banco; NÃO decide sobre ofertas.

    Enriquecimento paralelo: cada worker usa um Chrome efêmero com cookies do perfil logado,
    permitindo gerar o link de afiliado em paralelo sem travar o diretório do perfil.
    """

    def __init__(
        self,
        selenium_client: Optional[SeleniumClient] = None,
        user_data_dir: Optional[str] = None,
        profile_dir: Optional[str] = None,
        detach: bool = False,
        use_selenium: Optional[bool] = None,
    ):
        self.max_pages = int(get_config("ML_MAX_PAGES", "1"))
        self.delay_sec = float(get_config("ML_REQUEST_DELAY_SEC", "2"))
        # Número de sessões paralelas para enriquecer itens (1 = sequencial)
        self.max_enrich_workers = max(1, int(get_config("ML_ENRICH_WORKERS", "1")))
        # Guardar parâmetros para criar clientes adicionais quando necessário
        self._base_user_data_dir = user_data_dir
        self._base_profile_dir = profile_dir
        self._base_detach = detach
        # Determinar se deve usar Selenium (padrão True)
        if use_selenium is None:
            use_selenium_str = get_config("USE_SELENIUM", "true")
            self.use_selenium = use_selenium_str.lower() in ("true", "1", "yes", "sim")
        else:
            self.use_selenium = use_selenium
        # Inicializar Selenium apenas se necessário
        if self.use_selenium:
            self._init_selenium(selenium_client, user_data_dir, profile_dir, detach)
        else:
            # Configurar headers para requisições HTTP
            self._http_headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8',
                'cache-control': 'max-age=0',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
            }
            self._cookies = {
                '_d2id': '9b442ab8-dd44-4047-822f-6607b138f00f-n',
                '_mldataSessionId': '0524ed0c-e29c-46c2-b455-0cc59f53342a',
                '_csrf': 'D_7jfp4B21j-xj5KRDhjegGn',
                'c_ui-navigation': '6.6.152',
                'c_vpp': '1.162.0'
            }

    def _init_selenium(self, selenium_client, user_data_dir, profile_dir, detach):
        """
        - selenium_listing: navegação das listagens (não precisa login, perfil efêmero)
        - selenium_profile: sessão com perfil logado (exporta cookies e fallback)
        """
        # Perfil logado (para exportar cookies e fallback sequencial)
        self.selenium_profile = SeleniumClient(
            user_data_dir=(get_config("SELENIUM_USER_DATA_DIR", user_data_dir or "") or "").strip(),
            profile_dir=(get_config("SELENIUM_PROFILE_DIR", profile_dir or "") or "").strip(),
            detach=detach,
            #delay_sec=self.delay_sec,
            log_error=None,
        )
        try:
            # Exporta cookies + localStorage do perfil logado
            self._session_state = self.selenium_profile.export_session_state("https://www.mercadolivre.com.br")
        except Exception:
            self._session_state = {"cookies": [], "localStorage": {}}

        # Listagem (não usa perfil logado para evitar lock)
        self.selenium_listing = SeleniumClient(
            user_data_dir="",
            profile_dir="",
            detach=detach,
            #delay_sec=self.delay_sec,
            log_error=None,
        )
        # Opcional ainda importar no listing (não obrigatório)
        if self._session_state.get("cookies"):
            try:
                self.selenium_listing.import_session_state("https://www.mercadolivre.com.br", self._session_state)
            except Exception:
                pass

    def close(self):
        if self.use_selenium:
            try:
                self.selenium_listing.close()
            except Exception:
                pass
            try:
                self.selenium_profile.close()
            except Exception:
                pass

    # ===== Pool helpers =====
    def _make_client(self) -> SeleniumClient:
        """
        Cria um SeleniumClient efêmero e injeta cookies do perfil logado.
        Não usa user_data_dir para não bloquear o perfil.
        """
        cli = SeleniumClient(
            user_data_dir="",
            profile_dir="",
            detach=self._base_detach,
            #delay_sec=self.delay_sec,
            log_error=None,
        )
        # Injeta estado da sessão (cookies + localStorage)
        try:
            if getattr(self, "_session_state", None):
                cli.import_session_state("https://www.mercadolivre.com.br", self._session_state)
        except Exception:
            pass
        return cli

    def _serialize_cookies_for_header(self, cookies_list: List[dict]) -> str:
        """
        Converte lista de cookies (formato CDP) para string no formato de header Cookie.
        """
        if not cookies_list:
            return ""
        
        cookie_pairs = []
        for cookie in cookies_list:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if name and value:
                cookie_pairs.append(f"{name}={value}")
        
        return "; ".join(cookie_pairs)

    def _generate_affiliate_links_batch(self, urls: List[str]) -> Dict[str, Optional[str]]:
        """
        Gera links de afiliado em lote usando a API do Mercado Livre.
        
        Args:
            urls: Lista de URLs de produtos
            
        Returns:
            Dicionário mapeando URL original -> short_url
        """
        if not urls:
            return {}
        
        # Obter cookies da sessão logada
        cookies_str = ""
        if self.use_selenium and hasattr(self, "_session_state"):
            cookies_list = self._session_state.get("cookies", [])
            cookies_str = self._serialize_cookies_for_header(cookies_list)
        
        if not cookies_str:
            print("Aviso: Nenhum cookie disponível para gerar links de afiliado")
            return {url: None for url in urls}
        
        # Preparar headers
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'content-type': 'application/json',
            'origin': 'https://www.mercadolivre.com.br',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
            'Cookie': cookies_str
        }
        
        # Preparar body
        body = {
            "urls": urls,
            "tag": "promocoesdahora"
        }
        
        # Fazer request
        api_url = "https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink"
        
        try:
            print(f"Gerando {len(urls)} links de afiliado via API...")
            response = requests.post(api_url, headers=headers, json=body, timeout=30)
            response.raise_for_status()
            
            result_data = response.json()
            
            # Mapear URLs originais para short_urls
            url_map = {}
            if result_data.get("status") == 200 and "urls" in result_data:
                for item in result_data["urls"]:
                    origin_url = item.get("origin_url", "")
                    short_url = item.get("short_url", "")
                    if origin_url:
                        url_map[origin_url] = short_url if short_url else None
            
            # Preencher URLs que não retornaram com None
            for url in urls:
                if url not in url_map:
                    url_map[url] = None
            
            success_count = sum(1 for v in url_map.values() if v is not None)
            print(f"Links de afiliado gerados com sucesso: {success_count}/{len(urls)}")
            
            return url_map
            
        except Exception as e:
            print(f"Erro ao gerar links de afiliado via API: {e}")
            return {url: None for url in urls}

    def _enrich_with_http(self, item: dict) -> dict:
        """Enriquece item usando HTTP direto (sem Selenium)"""
        url = item.get("url_base") or ""
        if not url:
            return item
        
        print(f"Enriquecendo via HTTP: {url}")
        try:
            response = requests.get(url, headers=self._http_headers, cookies=self._cookies, timeout=15)
            response.raise_for_status()
            html = response.text
            time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            print(f"Erro ao buscar produto via HTTP {url}: {e}")
            return item
        
        soup = BeautifulSoup(html, "html.parser")
        data = self._extract__preloaded_json(soup)
        
        # Extrai dados adicionais do __PRELOADED_STATE__
        item["store_name"] = self._extract_store_name(data)
        item["seller_id"] = self._extract_seller_id(data)
        item["id_product"] = self._extract_id_product(data)
        item["preco_original"] = self._extract_price_before(data)
        item["preco_oferta"] = self._extract_price_after(data)
        item["desconto"] = self._extract_discount(data)
        item["nome_produto"] = self._extract_product_name(data)
        item["imagem_url"] = self._extract_product_image(data)
        item["seller_score"] = self._extract_seller_score(data)
                
        # No modo HTTP: não extrai url_afiliado_curta e ganho_real
        item["ganho_real"] = None
        item["url_afiliado_curta"] = None
        
        return item
    
    def _enrich_with_client_without_affiliate(self, client: SeleniumClient, item: dict) -> dict:
        """
        Enriquece item usando Selenium mas SEM gerar link de afiliado.
        Link de afiliado será gerado em lote via API posteriormente.
        """
        url = item.get("url_base") or ""
        if not url:
            return item
        
        html = client.get_page(
            url,
            wait_any_id=["__PRELOADED_STATE__"],
            timeout_sec=self.delay_sec,
        )
        soup = BeautifulSoup(html, "html.parser")
        data = self._extract__preloaded_json(soup)
        # Extrai dados adicionais do __PRELOADED_STATE__
        item["store_name"] = self._extract_store_name(data)
        item["seller_id"] = self._extract_seller_id(data)
        item["id_product"] = self._extract_id_product(data)
        item["preco_original"] = self._extract_price_before(data)
        item["preco_oferta"] = self._extract_price_after(data)
        item["desconto"] = self._extract_discount(data)
        item["nome_produto"] = self._extract_product_name(data)
        item["imagem_url"] = self._extract_product_image(data)
        item["seller_score"] = self._extract_seller_score(soup)
        # Extrai dados adicionais que nao estão no JSON
        item["ganho_real"] = self._extract_ganho_real(soup)
        # NÃO gerar url_afiliado_curta aqui - será feito via API em lote
        item["url_afiliado_curta"] = None
        return item

    def _enrich_with_client(self, client: SeleniumClient, item: dict) -> dict:
        # Worker reentrante: usa driver com cookies do perfil logado
        url = item.get("url_base") or ""
        if not url:
            return item
        
        html = client.get_page(
            url,
            wait_any_id=["__PRELOADED_STATE__"],
            timeout_sec=self.delay_sec,
        )
        soup = BeautifulSoup(html, "html.parser")
        data = self._extract__preloaded_json(soup)
        # Extrai dados adicionais do __PRELOADED_STATE__
        item["store_name"] = self._extract_store_name(data)
        item["seller_id"] = self._extract_seller_id(data)
        item["id_product"] = self._extract_id_product(data)
        item["preco_original"] = self._extract_price_before(data)
        item["preco_oferta"] = self._extract_price_after(data)
        item["desconto"] = self._extract_discount(data)
        item["nome_produto"] = self._extract_product_name(data)
        item["imagem_url"] = self._extract_product_image(data)
        item["seller_score"] = self._extract_seller_score(soup)
        # Extrai dados adicionais que nao estão no JSON
        item["ganho_real"] = self._extract_ganho_real(soup)
        item["url_afiliado_curta"] = client.get_short_affiliate_url(soup, delay=self.delay_sec) or None
        return item

    def _split_chunks(self, data: List[dict], parts: int) -> List[List[dict]]:
        if parts <= 1 or len(data) <= 1:
            return [data]
        size = max(1, math.ceil(len(data) / parts))
        return [data[i:i+size] for i in range(0, len(data), size)]

    def _enrich_parallel(self, offers: List[dict]) -> List[dict]:
        """
        Paraleliza o enriquecimento em N workers.
        No modo HTTP: usa requisições diretas sem Selenium.
        No modo Selenium: cada worker usa seu próprio driver efêmero com cookies do perfil logado.
        
        Após enriquecer os dados básicos, gera os links de afiliado em lote via API.
        """
        if not self.use_selenium:
            # Modo HTTP: enriquecimento sequencial
            out = []
            for it in offers:
                try:
                    out.append(self._enrich_with_http(it))
                except Exception as e:
                    print(f"Erro ao enriquecer item via HTTP: {e}")
                    out.append(it)
            # Gerar links de afiliado em lote via API (mesmo no modo HTTP)
            urls_to_generate = [item.get("url_base") for item in out if item.get("url_base")]
            if urls_to_generate:
                affiliate_map = self._generate_affiliate_links_batch(urls_to_generate)
                for item in out:
                    url_base = item.get("url_base")
                    if url_base and url_base in affiliate_map:
                        item["url_afiliado_curta"] = affiliate_map[url_base]
            return out
        
        # Modo Selenium (existente)
        results = []
        if self.max_enrich_workers <= 1 or len(offers) <= 1:
            # Sequencial usando o perfil logado diretamente
            for it in offers:
                # Não usar get_short_affiliate_url do Selenium, será feito via API depois
                enriched = self._enrich_with_client_without_affiliate(self.selenium_profile, it)
                results.append(enriched)
        else:
            workers = min(self.max_enrich_workers, len(offers))
            chunks = self._split_chunks(offers, workers)
            clients: List[SeleniumClient] = [self._make_client() for _ in range(len(chunks))]
            try:
                with ThreadPoolExecutor(max_workers=len(chunks)) as ex:
                    futures = []
                    for idx, chunk in enumerate(chunks):
                        client = clients[idx]
                        def run_chunk(items: List[dict], cli: SeleniumClient):
                            out = []
                            for it in items:
                                try:
                                    out.append(self._enrich_with_client_without_affiliate(cli, it))
                                except Exception:
                                    out.append(it)
                            return out
                        print(f"Iniciando worker {idx+1}/{len(chunks)} com {len(chunk)} itens...")
                        futures.append(ex.submit(run_chunk, chunk, client))
                    for fut in as_completed(futures):
                        try:
                            results.extend(fut.result())
                        except Exception:
                            pass
            finally:
                for cli in clients:
                    try:
                        cli.close()
                    except Exception:
                        pass
        
        # Gerar links de afiliado em lote via API para todos os itens
        urls_to_generate = [item.get("url_base") for item in results if item.get("url_base")]
        if urls_to_generate:
            affiliate_map = self._generate_affiliate_links_batch(urls_to_generate)
            for item in results:
                url_base = item.get("url_base")
                if url_base and url_base in affiliate_map:
                    item["url_afiliado_curta"] = affiliate_map[url_base]
        
        return results

    # ====================== Helpers de parsing ======================
    def _parse_price_brl(self, s: str) -> float:
        if not s:
            return 0.0
        try:
            s = s.strip()
            s = re.sub(r"[^\d,\.]", "", s)
            if s.count(",") == 1 and s.count(".") >= 1:
                s = s.replace(".", "")
            s = s.replace(",", ".")
            return float(s) if s else 0.0
        except Exception:
            return 0.0

    def _extract__preloaded_json(self, soup: BeautifulSoup) -> Optional[dict]:
        tag = soup.find("script", id="__PRELOADED_STATE__", attrs={"type": "application/json"})
        if not tag:
            print("Tag __PRELOADED_STATE__ não encontrada.")
            return None
        raw = tag.string or ""
        if not raw.strip():
            print("Tag __PRELOADED_STATE__ vazia.")
            return None
        try:
            print("Extraindo JSON do __PRELOADED_STATE__...")
            return json.loads(raw)
        except Exception:
            try:
                print("Tentando decodificar JSON com unicode_escape...")
                return json.loads(raw.encode("utf-8").decode("unicode_escape"))
            except Exception:
                print("Falha ao decodificar JSON do __PRELOADED_STATE__.")
                return None

    def _extract_seller_id(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o seller id a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.seller_id
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
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
                return None
        except Exception:
            return None

    def _extract_id_product(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o id do produto a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.product_id
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            id = node.get("id")
            if isinstance(id, str) and id.strip():
                return id.strip()
            return None
        except Exception:
            return None

    def _extract_store_name(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o nome da loja a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.seller_name
        """
        """
        Extrai o nome da loja a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.available_quantity.picker.track.melidata_event.event_data.seller_name
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
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
                    # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
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
            return None

    def _extract_price_before(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o nome da loja a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.seller_name
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
            if isinstance(node, dict):
                node = node.get("price", {})
                node = node.get("price", {})
                value = node.get("original_value") or node.get("original-value")
                if isinstance(value, (int, float)):
                    return float(value)
        except Exception:
            return None

    def _extract_price_after(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o nome da loja a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.seller_name
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
            if isinstance(node, dict):
                node = node.get("price", {})
                node = node.get("price", {})
                value = node.get("value")
                if isinstance(value, (int, float)):
                    return float(value)
        except Exception:
            return None

    def _extract_discount(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o nome da loja a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.seller_name
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
            if isinstance(node, dict):
                node = node.get("price", {})
                node = node.get("discount_label", {}) or node.get("discount-label", {})
                value = node.get("value")
                if isinstance(value, (int, float)):
                    return float(value)
        except Exception:
            return None

    def _extract_product_name(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o nome da loja a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.seller_name
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
            if isinstance(node, dict):
                node = node.get("share", {})
                name = node.get("title")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        except Exception:
            return None

    def _extract_product_image(self, data: Optional[dict]) -> Optional[str]:
        """
        Extrai o nome da loja a partir do JSON do __PRELOADED_STATE__.
        Caminho esperado:
        pageState.initialState.components.track.melidata_event.event_data.seller_name
        """
        if not data or not isinstance(data, dict):
            return None

        # Caminho direto
        try:
            node = data.get("pageState", {})
            node = node.get("initialState", {})
            node = node.get("components", {})
            # components pode vir como dict; se vier como lista, ignoramos aqui e caímos no fallback
            if isinstance(node, dict):
                node = node.get("share", {})
                node = node.get("picture", {})
                id = node.get("id")
                if isinstance(id, str) and id.strip():
                    return "https://http2.mlstatic.com/D_NQ_NP_" + id.strip() + "-O.webp"
        except Exception:
            return None

    def _extract_seller_score(self, data: Optional[dict]) -> Optional[int]:
        """
        Extrai o seller_score a partir do campo reputation_level do JSON.
        O campo vem no formato "5_green", "4_yellow", etc.
        Retorna apenas o primeiro número antes do underscore.
        """
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
                reputation_level = node.get("reputation_level")
                if reputation_level and isinstance(reputation_level, str):
                    # Extrair apenas o primeiro número antes do underscore
                    parts = reputation_level.split("_")
                    if parts and parts[0].isdigit():
                        return int(parts[0])
        except Exception:
            pass
        
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

    # ====================== Extração (listagem e produto) ======================
    def _fetch_ml_ofertas_page_http(self, page_num: int) -> str:
        """Busca página de ofertas via HTTP direto (sem Selenium)"""
        url = f"https://www.mercadolivre.com.br/ofertas?page={page_num}"
        print(f"Buscando página de ofertas {page_num} via HTTP: {url}")
        try:
            response = requests.get(url, headers=self._http_headers, cookies=self._cookies, timeout=15)
            response.raise_for_status()
            time.sleep(random.uniform(0.5, 1.5))
            return response.text
        except Exception as e:
            print(f"Erro ao buscar página {page_num} via HTTP: {e}")
            return ""
    
    def _fetch_ml_ofertas_page(self, page_num: int) -> str:
        """Busca página de ofertas (Selenium ou HTTP dependendo da configuração)"""
        if not self.use_selenium:
            return self._fetch_ml_ofertas_page_http(page_num)
        
        url = f"https://www.mercadolivre.com.br/ofertas?page={page_num}"
        # Usar o driver com perfil logado para evitar abrir uma nova janela não logada
        print(f"Buscando página de ofertas {page_num}: {url}")
        html = self.selenium_listing.get_page(
            url,
            wait_any_css=["h3.poly-component__title-wrapper", "main"],
            wait_any_xpath=["//h3"],
            timeout_sec=self.delay_sec,
        )
        #time.sleep(self.delay_sec + random.uniform(0.2, 0.7))
        return html

    def _parse_ml_offers(self, html: str) -> List[dict]:
        site = BeautifulSoup(html, "html.parser")
        links = site.find_all("a", class_="poly-component__title")
        print(f"  Itens encontrados na página: {len(links)}")
        results: List[dict] = []
        for link in links:
            href = link.get("href", "") or ""

            results.append({
                "source": "mercadolivre",
                "url_base": href,
            })
        return results

    # ====================== API principal ======================
    def run_collection(self) -> List[Dict]:
        results: List[dict] = []
        offers: List[dict] = []
        try:
            mode = "Selenium" if self.use_selenium else "HTTP direto (sem Selenium)"
            print(f"\n=== Modo de coleta: {mode} ===\n")
            
            for page in range(1, self.max_pages + 1):
                html = self._fetch_ml_ofertas_page(page)
                page_offers = self._parse_ml_offers(html)
                offers += page_offers  # concatena os resultados de cada página
            self.close()
            if offers:
                enriched_batch = self._enrich_parallel(offers)
                results.extend(enriched_batch)
        except Exception as e:
            print(f"Erro durante a coleta: {e}")
        return results