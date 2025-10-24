from __future__ import annotations

import re
import json
import time
import random
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

# Importar função para atualizar cookies
try:
    from backend.modules.utils.cookie_utils import update_all_site_cookies
except Exception:
    from ..utils.cookie_utils import update_all_site_cookies

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


class AmazonCollector(BaseCollector):
    """
    Extração de ofertas da Amazon Brasil.
    
    Passo 1: Acessar o site da Amazon via Selenium para exportar cookies atuais
    Passo 2: Acessar o site da Amazon no link de ofertas do dia via requests
             e copiar todos os links dos produtos (número de páginas configurável)
    Passo 3: Entrar em cada link e copiar informações via requests
    Passo 4: Enviar dados para o offer_processor.py
    
    Campos extraídos (mesmos do offer_processor.py):
    - url_base, id_product, seller_id, store_name
    - preco_original, preco_oferta, desconto
    - nome_produto, imagem_url, seller_score
    - url_afiliado_curta (opcional)
    """

    def __init__(
        self,
        selenium_client: Optional[SeleniumClient] = None,
        user_data_dir: Optional[str] = None,
        profile_dir: Optional[str] = None,
        detach: bool = False,
    ):
        # Configurações
        self.max_pages = int(get_config("AMAZON_MAX_PAGES", "1"))
        self.delay_sec = float(get_config("AMAZON_REQUEST_DELAY_SEC", "2"))
        
        # Guardar parâmetros para criar clientes
        self._base_user_data_dir = user_data_dir
        self._base_profile_dir = profile_dir
        self._base_detach = detach
        
        # Configurar headers para requisições HTTP
        self._http_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'max-age=0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
        }
        
        # Passo 1: Atualizar cookies da Amazon via Selenium
        print(f"Atualizando cookies da Amazon...")
        all_cookies = update_all_site_cookies(self._base_user_data_dir, self._base_profile_dir)
        amazon_cookies = all_cookies.get("https://www.amazon.com.br", {}).get("cookies", [])
        
        # Converter cookies para formato de string e dict
        self._cookies = "; ".join([f"{c['name']}={c['value']}" for c in amazon_cookies if 'name' in c and 'value' in c])
        
        # Parse cookies para dict (requests exige dict)
        self._cookies_dict = {}
        if self._cookies:
            for part in self._cookies.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    self._cookies_dict[k.strip()] = v.strip()
        
        self._cookie_header = self._cookies
        print(f"Cookies da Amazon atualizados: {len(self._cookies_dict)} cookies")

    def close(self):
        """Liberar recursos (não usado no modo HTTP)"""
        pass

    def _parse_price_brl(self, s: str) -> float:
        """Converte string de preço brasileiro para float"""
        if not s:
            return 0.0
        try:
            s = s.strip()
            # Remove R$ e outros caracteres não numéricos exceto , e .
            s = re.sub(r"[^\d,\.]", "", s)
            # Se tem vírgula e ponto, assume formato brasileiro (1.234,56)
            if "," in s and "." in s:
                s = s.replace(".", "")  # Remove separador de milhar
            # Converte vírgula decimal para ponto
            s = s.replace(",", ".")
            return float(s) if s else 0.0
        except Exception:
            return 0.0

    def _fetch_amazon_deals_page(self, page_num: int) -> str:
        """
        Passo 2: Busca página de ofertas da Amazon via HTTP
        URL de ofertas do dia da Amazon Brasil
        """
        # Amazon deals URL - pode variar, ajustar conforme necessário
        if page_num == 1:
            url = "https://www.amazon.com.br/deals"
        else:
            # Adicionar parâmetro de paginação
            url = f"https://www.amazon.com.br/deals?page={page_num}"
        
        print(f"Buscando página de ofertas da Amazon {page_num}: {url}")
        
        # Montar headers com cookies
        headers = dict(self._http_headers)
        if self._cookie_header:
            headers["Cookie"] = self._cookie_header
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            time.sleep(random.uniform(0.5, 1.5))
            return response.text
        except Exception as e:
            print(f"Erro ao buscar página {page_num} da Amazon: {e}")
            return ""

    def _parse_amazon_deals(self, html: str) -> List[dict]:
        """
        Passo 2: Extrai links de produtos da página de ofertas
        """
        soup = BeautifulSoup(html, "html.parser")
        
        # Amazon usa diferentes seletores para ofertas
        # Tentar múltiplas estratégias de busca
        product_links = []
        
        # Estratégia 1: Links diretos de produtos
        links = soup.find_all("a", href=re.compile(r"/dp/[A-Z0-9]{10}"))
        for link in links:
            href = link.get("href", "")
            if href and "/dp/" in href:
                # Converter para URL completa se for relativa
                if href.startswith("/"):
                    href = "https://www.amazon.com.br" + href
                # Limpar URL (remover query params desnecessários)
                href = href.split("?")[0]
                if href not in [p["url_base"] for p in product_links]:
                    product_links.append({
                        "source": "amazon",
                        "url_base": href,
                    })
        
        # Estratégia 2: Buscar por data-deal-id (ofertas específicas)
        deals = soup.find_all(attrs={"data-deal-id": True})
        for deal in deals:
            # Procurar link dentro do deal
            link = deal.find("a", href=re.compile(r"/dp/[A-Z0-9]{10}"))
            if link:
                href = link.get("href", "")
                if href and "/dp/" in href:
                    if href.startswith("/"):
                        href = "https://www.amazon.com.br" + href
                    href = href.split("?")[0]
                    if href not in [p["url_base"] for p in product_links]:
                        product_links.append({
                            "source": "amazon",
                            "url_base": href,
                        })
        
        print(f"  Produtos encontrados na página: {len(product_links)}")
        return product_links

    def _extract_product_data(self, url: str) -> Optional[dict]:
        """
        Passo 3: Extrai informações detalhadas de um produto
        Campos requeridos pelo offer_processor.py:
        - url_base, id_product, seller_id, store_name
        - preco_original, preco_oferta, desconto
        - nome_produto, imagem_url, seller_score
        - url_afiliado_curta (opcional)
        """
        print(f"Extraindo dados do produto: {url}")
        
        headers = dict(self._http_headers)
        if self._cookie_header:
            headers["Cookie"] = self._cookie_header
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            html = response.text
            time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            print(f"  ✗ Erro ao buscar produto: {e}")
            return None
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Extrair ID do produto da URL (ASIN)
        match = re.search(r"/dp/([A-Z0-9]{10})", url)
        id_product = match.group(1) if match else None
        
        if not id_product:
            print(f"  ✗ Não foi possível extrair ID do produto")
            return None
        
        # Extrair nome do produto
        nome_produto = None
        title_elem = soup.find("span", id="productTitle")
        if title_elem:
            nome_produto = title_elem.get_text(strip=True)
        
        # Extrair imagem do produto
        imagem_url = None
        img_elem = soup.find("img", id="landingImage") or soup.find("img", {"data-a-image-name": "landingImage"})
        if img_elem:
            imagem_url = img_elem.get("src") or img_elem.get("data-old-hires")
        
        # Extrair preço atual (oferta)
        preco_oferta = None
        # Tentar múltiplos seletores para preço
        price_whole = soup.find("span", class_="a-price-whole")
        price_fraction = soup.find("span", class_="a-price-fraction")
        if price_whole:
            price_str = price_whole.get_text(strip=True)
            if price_fraction:
                price_str += price_fraction.get_text(strip=True)
            preco_oferta = self._parse_price_brl(price_str)
        
        # Se não encontrou, tentar outro seletor
        if not preco_oferta:
            price_elem = soup.find("span", {"data-a-color": "price"})
            if price_elem:
                preco_oferta = self._parse_price_brl(price_elem.get_text(strip=True))
        
        # Extrair preço original (se houver desconto)
        preco_original = None
        original_price = soup.find("span", class_="a-price a-text-price")
        if original_price:
            price_text = original_price.find("span", class_="a-offscreen")
            if price_text:
                preco_original = self._parse_price_brl(price_text.get_text(strip=True))
        
        # Se não encontrou preço original, usar preço de oferta como original
        if not preco_original and preco_oferta:
            preco_original = preco_oferta
        
        # Calcular desconto
        desconto = 0.0
        if preco_original and preco_oferta and preco_original > preco_oferta:
            desconto = round(100.0 * (1 - (preco_oferta / preco_original)), 2)
        
        # Extrair informações do vendedor
        seller_name = "Amazon.com.br"  # Padrão
        seller_id = "AMAZON_BR"  # Padrão
        seller_score = 5  # Padrão para Amazon oficial
        
        # Tentar encontrar vendedor específico
        seller_elem = soup.find("a", id="sellerProfileTriggerId")
        if seller_elem:
            seller_name = seller_elem.get_text(strip=True)
            # Tentar extrair seller ID do link
            seller_link = seller_elem.get("href", "")
            seller_match = re.search(r"seller=([A-Z0-9]+)", seller_link)
            if seller_match:
                seller_id = seller_match.group(1)
        else:
            # Verificar se é vendido e entregue pela Amazon
            merchant_info = soup.find("div", id="merchant-info")
            if merchant_info and "Amazon" in merchant_info.get_text():
                seller_name = "Amazon.com.br"
                seller_id = "AMAZON_BR"
        
        # Validar campos obrigatórios
        if not all([nome_produto, preco_oferta]):
            print(f"  ✗ Campos obrigatórios ausentes - produto: {nome_produto}, preço: {preco_oferta}")
            return None
        
        item = {
            "url_base": url,
            "id_product": id_product,
            "seller_id": seller_id,
            "store_name": seller_name,
            "preco_original": preco_original,
            "preco_oferta": preco_oferta,
            "desconto": desconto,
            "nome_produto": nome_produto,
            "imagem_url": imagem_url,
            "seller_score": seller_score,
            "url_afiliado_curta": None,  # Amazon pode ter programa de afiliados, mas não implementado aqui
            "ganho_real": None,  # Não aplicável
        }
        
        print(f"  ✓ Produto extraído: {nome_produto} - R$ {preco_oferta}")
        return item

    def run_collection(self) -> List[Dict]:
        """
        Passo 4: Executa coleta completa
        Retorna lista de dicts para processar via offer_processor.py
        """
        results: List[dict] = []
        product_urls: List[dict] = []
        
        try:
            print(f"\n=== Iniciando coleta da Amazon (modo HTTP) ===\n")
            
            # Passo 2: Coletar links de produtos das páginas de ofertas
            for page in range(1, self.max_pages + 1):
                html = self._fetch_amazon_deals_page(page)
                if html:
                    page_offers = self._parse_amazon_deals(html)
                    product_urls.extend(page_offers)
                time.sleep(self.delay_sec)
            
            print(f"\n=== Total de {len(product_urls)} produtos encontrados ===\n")
            
            # Passo 3: Extrair dados de cada produto
            for product_info in product_urls:
                url = product_info.get("url_base")
                if url:
                    item = self._extract_product_data(url)
                    if item:
                        results.append(item)
                time.sleep(self.delay_sec)
            
            print(f"\n=== Coleta finalizada: {len(results)} produtos coletados com sucesso ===\n")
            
        except Exception as e:
            print(f"Erro durante a coleta da Amazon: {e}")
        
        return results
