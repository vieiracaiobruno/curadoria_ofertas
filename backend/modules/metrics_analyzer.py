
import requests
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import random # Para simular vendas

from ..models.models import Oferta, MetricaOferta
from ..db.database import DATABASE_URL, Base
from backend.utils.config import get_config

# Configuração do banco de dados
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Configurações de API (Substitua pelos seus tokens reais)
#BITLY_ACCESS_TOKEN = "SEU_BITLY_ACCESS_TOKEN"
BITLY_ACCESS_TOKEN = get_config("BITLY_ACCESS_TOKEN")  # era string fixa

class MetricsAnalyzer:
    def __init__(self, db_session):
        self.db = db_session

    def _get_bitly_clicks(self, bitly_link):
        if not BITLY_ACCESS_TOKEN or BITLY_ACCESS_TOKEN == "SEU_BITLY_ACCESS_TOKEN":
            print("ATENÇÃO: Token do Bitly não configurado. Não será possível obter cliques reais.")
            return random.randint(50, 500) # Simula cliques

        # A API do Bitly para obter cliques de um link específico é tipicamente:
        # GET /v4/bitlinks/{bitlink}/clicks
        # O bitlink deve ser o ID do link, não a URL completa.
        # Para simplificar, vamos assumir que o bitly_link é o ID ou que podemos extraí-lo.
        # Em uma implementação real, você precisaria armazenar o \'id\' do bitlink retornado na criação.
        
        # Exemplo simplificado: se o link for \'bit.ly/XYZ\', o ID seria \'XYZ\'
        bitlink_id = bitly_link.split("/")[-1]

        headers = {
            "Authorization": f"Bearer {BITLY_ACCESS_TOKEN}"
        }
        try:
            response = requests.get(f"https://api-ssl.bitly.com/v4/bitlinks/{bitlink_id}/clicks", headers=headers)
            response.raise_for_status()
            data = response.json()
            # A estrutura da resposta pode variar, geralmente \'link_clicks\' é o total
            total_clicks = data.get("link_clicks", 0)
            return total_clicks
        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter cliques do Bitly para {bitly_link}: {e}")
            return random.randint(50, 500) # Simula cliques em caso de erro

    def _get_affiliate_sales(self, oferta_id, tracking_id=None):
        # Esta é uma função mock para simular a obtenção de vendas de plataformas de afiliados.
        # Na realidade, isso envolveria:
        # 1. Integração com APIs de relatórios da Amazon Associates, Mercado Livre Afiliados, etc.
        # 2. Uso do \'tracking_id\' (subId) que foi anexado à URL de afiliado para identificar a venda.
        # 3. Processamento de relatórios CSV baixados manualmente (se não houver API).
        print(f"Simulando vendas para oferta {oferta_id}...")
        return random.randint(0, 5) # Simula entre 0 e 5 vendas por oferta

    def analyze_metrics(self):
        print("Iniciando análise de métricas de ofertas publicadas...")
        ofertas_publicadas = self.db.query(Oferta).filter(Oferta.status == "PUBLICADO").all()

        for oferta in ofertas_publicadas:
            # Pega o link curto do Bitly
            bitly_link = oferta.url_afiliado_curta
            if not bitly_link:
                print(f"Oferta {oferta.id} não possui link Bitly. Pulando métricas.")
                continue

            # Coleta cliques
            cliques = self._get_bitly_clicks(bitly_link)

            # Coleta vendas (simulado)
            # Em uma implementação real, você passaria o subId/tracking_id da URL de afiliado
            vendas = self._get_affiliate_sales(oferta.id, tracking_id="algum_sub_id_da_oferta")

            # Atualiza ou cria o registro de métricas
            metrica = self.db.query(MetricaOferta).filter_by(oferta_id=oferta.id).first()
            if not metrica:
                metrica = MetricaOferta(
                    oferta_id=oferta.id,
                    cliques=cliques,
                    vendas=vendas,
                    data_atualizacao=datetime.now()
                )
                self.db.add(metrica)
            else:
                metrica.cliques = cliques
                metrica.vendas = vendas
                metrica.data_atualizacao = datetime.now()
            
            self.db.commit()
            print(f"Métricas atualizadas para oferta {oferta.id}: Cliques={cliques}, Vendas={vendas}")

        print("Análise de métricas concluída.")

if __name__ == "__main__":
    db_session = SessionLocal()
    analyzer = MetricsAnalyzer(db_session)
    analyzer.analyze_metrics()
    db_session.close()


