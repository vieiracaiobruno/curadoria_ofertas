import requests
from bs4 import BeautifulSoup
from datetime import datetime
from sqlalchemy.orm import Session
from ..models.models import Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag
from ..db.database import SessionLocal

class Collector:
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.tag_keywords = {
            'informatica': ['notebook', 'computador', 'ssd', 'memória ram', 'processador', 'monitor', 'teclado', 'mouse', 'placa de vídeo'],
            'gamer': ['gamer', 'rtx', 'geforce', 'radeon', 'console', 'playstation', 'xbox', 'nintendo', 'headset gamer'],
            'celular': ['iphone', 'galaxy', 'xiaomi', 'motorola', 'smartphone', 'celular', 'android', 'ios'],
            'eletrodomestico': ['geladeira', 'fogão', 'micro-ondas', 'air fryer', 'batedeira', 'liquidificador', 'lava-louças', 'aspirador de pó'],
            'tv': ['tv', 'televisão', 'smart tv', 'qled', 'oled'],
            'audio': ['fone de ouvido', 'caixa de som', 'soundbar', 'bluetooth'],
            'casa': ['cama', 'mesa', 'banho', 'sofa', 'armario', 'decoracao', 'utensilios'],
            'esporte': ['tenis', 'roupa esportiva', 'bicicleta', 'fitness', 'suplemento'],
            'livros': ['livro', 'e-book', 'literatura', 'ficcao', 'nao-ficcao'],
            'brinquedos': ['brinquedo', 'boneca', 'carrinho', 'lego', 'jogos de tabuleiro']
        }

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

    def _save_product_and_offer(self, product_data, loja_confiavel):
        # Verifica se o produto já existe
        produto = self.db_session.query(Produto).filter_by(product_id_loja=product_data['product_id_loja']).first()

        if not produto:
            produto = Produto(
                product_id_loja=product_data['product_id_loja'],
                nome_produto=product_data['nome_produto'],
                url_base=product_data['url_base'],
                imagem_url=product_data.get('imagem_url')
            )
            self.db_session.add(produto)
            self.db_session.flush() # Para obter o ID do produto antes do commit

            # Sugere e associa tags
            suggested_tags = self._suggest_tags(product_data['nome_produto'])
            for tag in suggested_tags:
                produto.tags.append(tag)
            self.db_session.commit()
            self.db_session.refresh(produto)
        else:
            # Atualiza nome e imagem se houver mudança
            produto.nome_produto = product_data['nome_produto']
            if product_data.get('imagem_url'):
                produto.imagem_url = product_data['imagem_url']
            self.db_session.commit()
            self.db_session.refresh(produto)

        # Registra o preço no histórico
        historico = HistoricoPreco(
            produto_id=produto.id,
            loja_id=loja_confiavel.id,
            preco=product_data['preco_oferta'],
            data_verificacao=datetime.now()
        )
        self.db_session.add(historico)

        # Cria a oferta pendente
        oferta = Oferta(
            produto_id=produto.id,
            loja_id=loja_confiavel.id,
            preco_original=product_data.get('preco_original'),
            preco_oferta=product_data['preco_oferta'],
            url_afiliado_longa=product_data['url_afiliado_longa'],
            data_encontrado=datetime.now(),
            data_validade=product_data.get('data_validade'),
            status="PENDENTE_APROVACAO"
        )
        self.db_session.add(oferta)
        self.db_session.commit()

    def _scrape_mercadolivre(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status() # Levanta HTTPError para 4xx/5xx respostas
            soup = BeautifulSoup(response.content, 'html.parser')

            title = soup.find('h1', class_='ui-pdp-title').text.strip() if soup.find('h1', class_='ui-pdp-title') else 'N/A'
            
            price_element = soup.find('span', class_='andes-money-amount__fraction')
            price = float(price_element.text.replace('.', '').replace(',', '.')) if price_element else 0.0
            
            original_price_element = soup.find('s', class_='andes-money-amount__fraction')
            original_price = float(original_price_element.text.replace('.', '').replace(',', '.')) if original_price_element else price
            
            image_element = soup.find('img', class_='ui-pdp-image')
            image_url = image_element['src'] if image_element and 'src' in image_element.attrs else None

            discount = ((original_price - price) / original_price) * 100 if original_price > 0 else 0

            # Extrair product_id_loja do URL
            product_id_loja = url.split('MLB-')[-1].split('-')[0] if 'MLB-' in url else None

            return {
                'product_id_loja': product_id_loja,
                'nome_produto': title,
                'preco_oferta': price,
                'preco_original': original_price,
                'desconto': discount,
                'url_base': url,
                'url_afiliado_longa': url, # Substituir por URL de afiliado real
                'imagem_url': image_url,
                'data_validade': None
            }
        except requests.exceptions.RequestException as e:
            print(f"Erro de requisição ao raspar Mercado Livre ({url}): {e}")
            return None
        except Exception as e:
            print(f"Erro ao processar HTML do Mercado Livre ({url}): {e}")
            return None

    def _scrape_amazon(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            title = soup.find('span', id='productTitle').text.strip() if soup.find('span', id='productTitle') else 'N/A'
            
            price_whole = soup.find('span', class_='a-price-whole')
            price_fraction = soup.find('span', class_='a-price-fraction')
            price = 0.0
            if price_whole and price_fraction:
                price_str = price_whole.text.replace('.', '') + '.' + price_fraction.text
                price = float(price_str)
            
            original_price_element = soup.find('span', class_='a-text-strike')
            original_price = float(original_price_element.text.replace('R$', '').replace('.', '').replace(',', '.').strip()) if original_price_element else price

            image_element = soup.find('img', id='landingImage')
            image_url = image_element['src'] if image_element and 'src' in image_element.attrs else None

            discount = ((original_price - price) / original_price) * 100 if original_price > 0 else 0

            # Extrair product_id_loja do URL (ASIN para Amazon)
            product_id_loja = url.split('/dp/')[-1].split('/')[0] if '/dp/' in url else None

            return {
                'product_id_loja': product_id_loja,
                'nome_produto': title,
                'preco_oferta': price,
                'preco_original': original_price,
                'desconto': discount,
                'url_base': url,
                'url_afiliado_longa': url, # Substituir por URL de afiliado real
                'imagem_url': image_url,
                'data_validade': None
            }
        except requests.exceptions.RequestException as e:
            print(f"Erro de requisição ao raspar Amazon ({url}): {e}")
            return None
        except Exception as e:
            print(f"Erro ao processar HTML da Amazon ({url}): {e}")
            return None

    def run_collection(self):
        print("Iniciando coleta de ofertas reais...")
        lojas_confiaveis = self.db_session.query(LojaConfiavel).filter_by(ativa=True).all()

        # Exemplo de URLs reais para teste (substitua por URLs dinâmicas ou de pesquisa)
        # É crucial que estas URLs sejam de produtos reais e que você tenha permissão para raspá-las.
        # Para um sistema robusto, você precisaria de uma estratégia para encontrar URLs de ofertas.
        example_urls = {
            'Mercado Livre': [
                'https://produto.mercadolivre.com.br/MLB-2678886440-notebook-gamer-dell-g15-5530-i7-13650hx-rtx-3050-6gb-16gb-ssd512-_JM',
                'https://produto.mercadolivre.com.br/MLB-3566765064-celular-xiaomi-redmi-note-13-pro-5g-8gb-ram-256gb-global-_JM'
            ],
            'Amazon': [
                'https://www.amazon.com.br/Echo-Dot-5%C2%AA-Gera%C3%A7%C3%A3o-Smart-Speaker-com-Alexa-Cor-Preta/dp/B0B3F11G1C',
                'https://www.amazon.com.br/Monitor-Samsung-Odyssey-G32A-FHD/dp/B0B3F11G1C'
            ]
        }

        for loja in lojas_confiaveis:
            if loja.plataforma == "Mercado Livre":
                for url in example_urls.get('Mercado Livre', []):
                    data = self._scrape_mercadolivre(url)
                    if data:
                        self._save_product_and_offer(data, loja)
                        print(f"Oferta do ML coletada: {data['nome_produto']}")
            elif loja.plataforma == "Amazon":
                for url in example_urls.get('Amazon', []):
                    data = self._scrape_amazon(url)
                    if data:
                        self._save_product_and_offer(data, loja)
                        print(f"Oferta da Amazon coletada: {data['nome_produto']}")
        print("Coleta de ofertas reais concluída.")

if __name__ == "__main__":
    db_session = SessionLocal()
    collector = Collector(db_session)
    collector.run_collection()
    db_session.close()


