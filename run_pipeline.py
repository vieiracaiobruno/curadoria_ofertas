#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RunPipeline (classe) — orquestra a curadoria de ofertas:
1) Coleta (Mercado Livre via Selenium + BeautifulSoup)
2) Processamento/Persistência (estrutura de ofertas)
3) Validação
4) Publicação
5) Métricas
"""
import os
import logging
import sys

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# DB

from backend.db.database import SessionLocal
from backend.modules.collectors.ml_collector import MLCollector
from backend.modules.collectors.amazon_collector import AmazonCollector
from backend.modules.services.offer_processor import OfferProcessor
from backend.modules.services.validator import Validator
from backend.modules.services.publisher import Publisher
from backend.modules.services.metrics_analyzer import MetricsAnalyzer
from backend.modules.utils.config import get_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

class RunPipeline:
    def __init__(self):
        self.db = SessionLocal()

    def run(self):
        try:
            logging.info("=== Iniciando Pipeline (classe) de Curadoria de Ofertas ===")

            all_items = []

            # 1a) Coleta (Mercado Livre)
            enable_ml = (get_config("ENABLE_ML_COLLECTOR", "true") or "true").lower() in {"1", "true", "yes", "y"}
            if enable_ml:
                logging.info("Iniciando coleta (Mercado Livre)…")
                ml_collector = MLCollector()
                ml_items = ml_collector.run_collection()
                logging.info(f"Coleta ML concluída. Itens extraídos: {len(ml_items)}")
                all_items.extend(ml_items)
            else:
                logging.info("Coleta do Mercado Livre desabilitada (ENABLE_ML_COLLECTOR=false)")

            # 1b) Coleta (Amazon)
            enable_amazon = (get_config("ENABLE_AMAZON_COLLECTOR", "false") or "false").lower() in {"1", "true", "yes", "y"}
            if enable_amazon:
                logging.info("Iniciando coleta (Amazon)…")
                amazon_collector = AmazonCollector()
                amazon_items = amazon_collector.run_collection()
                logging.info(f"Coleta Amazon concluída. Itens extraídos: {len(amazon_items)}")
                all_items.extend(amazon_items)
            else:
                logging.info("Coleta da Amazon desabilitada (ENABLE_AMAZON_COLLECTOR=false)")

            logging.info(f"Total de itens coletados: {len(all_items)}")

            # 2) Processamento/Persistência (estrutura de ofertas)
            logging.info("Processando itens (persistência/estrutura de ofertas)…")
            processor = OfferProcessor(self.db)
            for it in all_items:
                processor.process_item(it)
            logging.info(f"Processamento concluído. Stats: {processor.stats}")

            # 3) Validação — mantém sua lógica atual
            logging.info("Iniciando validação…")
            validator = Validator(self.db)
            validator.run_validation()
            logging.info("Validação concluída.")

            # 4) Publicação — mantém sua lógica atual
            logging.info("Iniciando publicação…")
            publisher = Publisher(self.db)
            publisher.run_publication()
            logging.info("Publicação concluída.")

            # 5) Métricas — mantém sua lógica atual
            logging.info("Iniciando análise de métricas…")
            metrics_analyzer = MetricsAnalyzer(self.db)
            metrics_analyzer.analyze_metrics()
            logging.info("Análise de métricas concluída.")

            self.db.commit()
            logging.info("=== Pipeline executado com sucesso ===")
        except Exception as e:
            self.db.rollback()
            logging.exception(f"Erro durante a execução do pipeline: {e}")
            raise
        finally:
            self.db.close()


if __name__ == "__main__":
    runner = RunPipeline()
    runner.run()
