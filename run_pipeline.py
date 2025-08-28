#!/usr/bin/env python3
"""
Pipeline completo de curadoria de ofertas
"""

import os
import sys
import logging
from datetime import datetime

# Adiciona o diretório raiz do projeto ao sys.path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from backend.db.database import SessionLocal, engine, Base
from backend.models.models import Usuario, Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta, HistoricoPreco # Importar todos os modelos
from backend.modules.collector import Collector
from backend.modules.validator import Validator
from backend.modules.publisher import Publisher
from backend.modules.metrics_analyzer import MetricsAnalyzer

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format=\'%(asctime)s - %(levelname)s - %(message)s\

    handlers=[
        logging.FileHandler(\"/home/ubuntu/curadoria_ofertas/pipeline.log\"),
        logging.StreamHandler()
    ]
)

def run_pipeline():
    db = SessionLocal()
    try:
        logging.info("=== Iniciando Pipeline de Curadoria de Ofertas ===")

        # Garante que as tabelas existam (pode ser movido para um script de setup)
        # Esta linha deve ser executada apenas uma vez no setup inicial do banco de dados
        # Base.metadata.create_all(bind=engine)

        # 1. Coleta de dados
        logging.info("Iniciando coleta de ofertas...")
        collector = Collector(db)
        collector.run_collection()
        logging.info("Coleta de ofertas concluída.")

        # 2. Validação
        logging.info("Iniciando validação de ofertas...")
        validator = Validator(db)
        validator.run_validation()
        logging.info("Validação de ofertas concluída.")

        # 3. Publicação
        logging.info("Iniciando publicação de ofertas...")
        publisher = Publisher(db)
        publisher.run_publication()
        logging.info("Publicação de ofertas concluída.")

        # 4. Análise de Métricas (opcional, pode ser executado separadamente)
        logging.info("Iniciando análise de métricas...")
        metrics_analyzer = MetricsAnalyzer(db)
        metrics_analyzer.run_analysis()
        logging.info("Análise de métricas concluída.")

        db.commit()
        logging.info("=== Pipeline executado com sucesso ===")

    except Exception as e:
        db.rollback()
        logging.error(f"Erro durante a execução do pipeline: {e}", exc_info=True)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_pipeline()


