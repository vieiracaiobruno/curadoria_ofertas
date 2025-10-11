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
from backend.modules.services.link_service import LinkService
from backend.modules.services.link_parser import LinkParser
from backend.modules.validator import Validator
from backend.modules.publisher import Publisher
from backend.modules.metrics_analyzer import MetricsAnalyzer


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

            # 1) Coleta de Links (Mercado Livre)
            logging.info("Fase 1: Coletando links (Mercado Livre / Selenium)…")
            ml_collector = MLCollector()
            links = ml_collector.run_collection()
            logging.info(f"Coleta de links concluída. Links encontrados: {len(links)}")

            # 2) Persistência dos Links
            logging.info("Fase 2: Salvando links na tabela links_coleta…")
            link_service = LinkService(self.db)
            inserted = link_service.save_links(links, source="mercadolivre")
            logging.info(f"Links salvos: {inserted} novos, {len(links) - inserted} já existiam")

            # 3) Limpeza de Links Expirados (TTL)
            logging.info("Fase 3: Limpando links expirados (TTL 24h)…")
            expired = link_service.cleanup_expired_links(ttl_hours=24)
            logging.info(f"Links expirados removidos: {expired}")

            # 4) Parsing Paralelo de Links Ativos
            logging.info("Fase 4: Parsing paralelo de links ativos…")
            link_parser = LinkParser(self.db)
            try:
                parse_stats = link_parser.parse_active_links(source="mercadolivre")
                logging.info(f"Parsing concluído. Stats: {parse_stats}")
            finally:
                link_parser.cleanup()

            # 5) Validação — mantém sua lógica atual
            logging.info("Fase 5: Validação de ofertas…")
            validator = Validator(self.db)
            validator.run_validation()
            logging.info("Validação concluída.")

            # 6) Publicação — mantém sua lógica atual
            logging.info("Fase 6: Publicação de ofertas…")
            publisher = Publisher(self.db)
            publisher.run_publication()
            logging.info("Publicação concluída.")

            # 7) Métricas — mantém sua lógica atual
            logging.info("Fase 7: Análise de métricas…")
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
