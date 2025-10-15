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
import html as _html
from urllib.parse import urlparse, parse_qs, unquote
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


# Lista de sites de coleta para exportar cookies
COLLECTION_SITES = [
    "https://www.mercadolivre.com.br"
]


def update_all_site_cookies(user_data_dir: Optional[str] = None, profile_dir: Optional[str] = None) -> Dict[str, dict]:
    """
    Função genérica para atualizar cookies de todos os sites de coleta.
    Abre uma sessão do Chrome com o perfil logado, navega em cada site e exporta os cookies.
    
    Args:
        user_data_dir: Diretório de dados do usuário do Chrome
        profile_dir: Diretório do perfil do Chrome
        
    Returns:
        Dict com os cookies exportados de cada site: {url: {cookies: [...], localStorage: {...}}}
    """
    from backend.modules.utils.selenium_client import SeleniumClient
    from backend.modules.utils.config import get_config
    
    user_data = (get_config("SELENIUM_USER_DATA_DIR", user_data_dir or "") or "").strip()
    profile = (get_config("SELENIUM_PROFILE_DIR", profile_dir or "") or "").strip()
    
    print(f"Abrindo sessão do Chrome com perfil logado para exportar cookies...")
    selenium_client = SeleniumClient(
        user_data_dir=user_data,
        profile_dir=profile,
        detach=False,
        log_error=None,
    )
    
    all_cookies = {}
    try:
        for site_url in COLLECTION_SITES:
            print(f"  Exportando cookies de: {site_url}")
            try:
                session_state = selenium_client.export_session_state(site_url)
                all_cookies[site_url] = session_state
                print(f"    ✓ {len(session_state.get('cookies', []))} cookies exportados")
            except Exception as e:
                print(f"    ✗ Erro ao exportar cookies de {site_url}: {e}")
                all_cookies[site_url] = {"cookies": [], "localStorage": {}}
    finally:
        try:
            selenium_client.close()
        except Exception:
            pass
    
    return all_cookies


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
            # Atualizar cookies antes de fazer a chamada
            print(f"Atualizando cookies para API de afiliados...")
            all_cookies = update_all_site_cookies(self._base_user_data_dir, self._base_profile_dir)
            ml_cookies = all_cookies.get("https://www.mercadolivre.com.br", {}).get("cookies", [])
        
            # Converter cookies para formato de string
            self._cookies = "; ".join([f"{c['name']}={c['value']}" for c in ml_cookies if 'name' in c and 'value' in c])
            #print("Cookies atualizados: ", self._cookies)

            # Parse cookies para dict (requests exige dict se usado no argumento cookies)
            self._cookies_dict = {}
            if self._cookies:
                for part in self._cookies.split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        self._cookies_dict[k.strip()] = v.strip()
            # Opcional: manter header pronto
            self._cookie_header = self._cookies

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

    def _clean_url(self, url: str) -> str:
        """
        Remove parâmetros de query da URL, mantendo apenas a URL base do produto.
        Ex: https://produto.mercadolivre.com.br/MLB-123-produto_JM?searchVariation=123#extras
            -> https://produto.mercadolivre.com.br/MLB-123-produto_JM
        """
        if not url:
            return url
        # Remove fragment (#...) e query parameters (?...)
        url = url.split('#')[0].split('?')[0]
        return url
    
    def _get_affiliate_links_batch(self, urls: List[str], tag: str = "promocoesdahora") -> Dict[str, str]:
        """
        Chama a API do Mercado Livre para obter links de afiliado curtos em lote.
        
        Args:
            urls: Lista de URLs de produtos
            tag: Tag do afiliado
            
        Returns:
            Dict mapeando origin_url -> short_url (usando URLs originais como chave)
        """
        if not urls:
            return {}
        
        # Limpar URLs antes de enviar
        clean_urls = [self._clean_url(url) for url in urls]
        
        api_url = "https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink"
        # Corrigir: montar header Cookie a partir do dict de cookies, se disponível
        cookie_header = ""
        if hasattr(self, "_cookies_dict") and self._cookies_dict:
            cookie_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
        elif hasattr(self, "_cookies") and self._cookies:
            cookie_header = self._cookies

        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'content-type': 'application/json',
            'origin': 'https://www.mercadolivre.com.br',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
        }
        if cookie_header:
            headers['Cookie'] = cookie_header
        
        body = {
            "urls": clean_urls,
            "tag": tag
        }

        # Gerar comando CURL equivalente para debug
        curl_command = (
            f"curl -X POST '{api_url}' "
            f"-H 'accept: {headers['accept']}' "
            f"-H 'accept-language: {headers['accept-language']}' "
            f"-H 'content-type: {headers['content-type']}' "
            f"-H 'origin: {headers['origin']}' "
            f"-H 'user-agent: {headers['user-agent']}' "
            f"-H 'Cookie: {headers.get('Cookie','')}' "
            f"-d '{json.dumps(body, ensure_ascii=False)}'"
        )
        #print("\n[DEBUG] Comando CURL equivalente:")
        #print(curl_command)
        #print("-" * 100)
        
        print(f"Chamando API de afiliados para {len(clean_urls)} URLs...")
        try:
            response = requests.post(api_url, headers=headers, json=body, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Mapear URL original -> short_url (importante: mapear usando as URLs originais, não as limpas)
            url_mapping = {}
            for idx, item in enumerate(data.get("urls", [])):
                short_url = item.get("short_url")
                if short_url and idx < len(urls):
                    # Mapear usando a URL original (com query params) como chave
                    url_mapping[urls[idx]] = short_url
            
            print(f"  ✓ {len(url_mapping)} links de afiliado obtidos com sucesso")
            return url_mapping
            
        except Exception as e:
            print(f"  ✗ Erro ao chamar API de afiliados: {e}")
            return {}
    
    def _enrich_with_http(self, item: dict) -> dict:
        """Enriquece item usando HTTP direto (sem Selenium)"""
        url = item.get("url_base") or ""
        if not url:
            return item
        
        print(f"Enriquecendo via HTTP: {url}")
        try:
            # Usa dict de cookies (requests exige dict ou CookieJar)
            cookies_dict = getattr(self, "_cookies_dict", None)
            headers = dict(self._http_headers)
            if getattr(self, "_cookie_header", None):
                headers["Cookie"] = self._cookie_header
            response = requests.get(
                url,
                headers=headers,
                cookies=cookies_dict if isinstance(cookies_dict, dict) else None,
                timeout=15
            )
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
        
        # Extrai ganho_real do HTML
        item["ganho_real"] = self._extract_ganho_real(soup)
        
        # url_afiliado_curta será preenchido em lote posteriormente
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
        Limitação: a API de afiliados aceita no máximo 30 URLs por chamada -> enviar em lotes de 30.
        """
        if not self.use_selenium:
            # Modo HTTP: enriquecimento sequencial (pode ser paralelizado no futuro se necessário)
            out = []
            for it in offers:
                try:
                    out.append(self._enrich_with_http(it))
                except Exception as e:
                    print(f"Erro ao enriquecer item via HTTP: {e}")
                    out.append(it)
            
            # Após enriquecer todos os itens, buscar links de afiliado em lotes de 30
            print(f"\n=== Buscando links de afiliado em lote para {len(out)} itens (máx 30 por requisição) ===")
            urls_to_fetch = [item["url_base"] for item in out if item.get("url_base")]
            affiliate_mapping: Dict[str, str] = {}
            batch_size = 30
            for start in range(0, len(urls_to_fetch), batch_size):
                chunk = urls_to_fetch[start:start + batch_size]
                print(f"  -> Lote {start // batch_size + 1}: {len(chunk)} URLs")
                try:
                    mapping_chunk = self._get_affiliate_links_batch(chunk)
                    affiliate_mapping.update(mapping_chunk)
                except Exception as e:
                    print(f"    ✗ Erro no lote: {e}")
                time.sleep(0.5)  # pequeno intervalo para evitar throttling
            
            # Atualizar os itens com os links de afiliado obtidos
            total_links = 0
            for item in out:
                url_base = item.get("url_base")
                if url_base and url_base in affiliate_mapping:
                    item["url_afiliado_curta"] = affiliate_mapping[url_base]
                    total_links += 1
            print(f"=== Finalizado: {total_links} links de afiliado atribuídos ===\n")
            return out
        
        # Modo Selenium (existente)
        if self.max_enrich_workers <= 1 or len(offers) <= 1:
            out = []
            for it in offers:
                out.append(self._enrich_with_client(self.selenium_profile, it))
            return out

        workers = min(self.max_enrich_workers, len(offers))
        chunks = self._split_chunks(offers, workers)
        clients: List[SeleniumClient] = [self._make_client() for _ in range(len(chunks))]
        results: List[dict] = []
        try:
            with ThreadPoolExecutor(max_workers=len(chunks)) as ex:
                futures = []
                for idx, chunk in enumerate(chunks):
                    client = clients[idx]
                    def run_chunk(items: List[dict], cli: SeleniumClient):
                        out_local = []
                        for it in items:
                            try:
                                out_local.append(self._enrich_with_client(cli, it))
                            except Exception:
                                out_local.append(it)
                        return out_local
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
                id = node.get("official_store_id") or node.get("official-store-id")
                if isinstance(id, int):
                    return str(id)
                else:
                    id = node.get("seller_id") or node.get("seller-id")
                    if isinstance(id, int):
                        return str(id)
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

        # Montar headers (adiciona Cookie aqui)
        headers = dict(self._http_headers or {})
        if getattr(self, "_cookie_header", None):
            headers["Cookie"] = self._cookie_header

        # Montar headers em string legível para curl
        headers_str = " ".join([f"-H '{k}: {v}'" for k, v in headers.items()])

        #curl_command = f"curl -X GET '{url}' {headers_str}"
        #print("\n[DEBUG] Comando CURL equivalente:")
        #print(curl_command)
        #print("-" * 100)

        try:
            # Removido: cookies=self._cookies (string) -> causava "string indices must be integers"
            # Use somente headers com 'Cookie' ou cookies=dict
            response = requests.get(url, headers=headers, timeout=15)
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
        
        def _resolve_click1(href: str) -> str:
            """
            Se o href for um link de redirecionamento (click1.mercadolivre...),
            extrai o parâmetro 'url', decodifica percent-encoding e entidades HTML.
            """
            if not href:
                return href
            # Normaliza entidades HTML primeiro (alguns &amp; podem quebrar parsing de query)
            href_clean = _html.unescape(href)
            try:
                parsed = urlparse(href_clean)
                if "click1.mercadolivre.com.br" not in parsed.netloc:
                    return href  # não é link de redirecionamento
                qs = parse_qs(parsed.query)
                target = qs.get("url", [None])[0]
                if not target:
                    return href
                # Decodifica múltiplas vezes se necessário
                prev = target
                for _ in range(3):
                    cur = unquote(prev)
                    if cur == prev:
                        break
                    prev = cur
                target_decoded = _html.unescape(prev)
                return target_decoded
            except Exception:
                return href

        results: List[dict] = []
        for link in links:
            href = link.get("href", "") or ""
            final_url = _resolve_click1(href)
            results.append({
                "source": "mercadolivre",
                "url_base": final_url,
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