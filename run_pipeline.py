#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RunPipeline (classe) — orquestra a curadoria de ofertas:
1) Coleta de Links (salva na tabela links_coleta)
2) Parsing de Links (lê da tabela e faz enriquecimento paralelo)
3) Processamento/Persistência (estrutura de ofertas)
4) Validação
5) Publicação
6) Métricas
"""
import os
import logging
import sys

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# DB

from backend.db.database import SessionLocal
from backend.modules.collectors.ml_collector import MLCollector
from backend.modules.services.link_collector_service import LinkCollectorService
from backend.modules.services.link_parser import LinkParser
from backend.modules.parsers.ml_parser import MLParser
from backend.modules.services.offer_processor import OfferProcessor
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

            # 1) Coleta de Links (apenas URLs, sem enriquecimento)
            logging.info("Fase 1: Coletando links...")
            ml_collector = MLCollector()
            links = ml_collector.run_collection()
            logging.info(f"Links coletados: {len(links)}")

            # 2) Salvar links na tabela links_coleta
            logging.info("Fase 2: Salvando links na tabela...")
            link_collector_svc = LinkCollectorService(self.db)
            save_stats = link_collector_svc.save_links(links)
            logging.info(f"Links salvos - Stats: {save_stats}")

            # 3) Parsing de Links (lê da tabela e processa em paralelo)
            logging.info("Fase 3: Parseando links da tabela...")
            link_parser = LinkParser(self.db)
            
            # Limpar links expirados (TTL)
            link_parser.cleanup_expired_links()
            
            # Buscar links pendentes
            pending_links = link_parser.get_pending_links()
            logging.info(f"Links pendentes para parse: {len(pending_links)}")
            
            if pending_links:
                # Parser específico para ML
                ml_parser = MLParser()
                
                # Função factory para o parser
                def parse_link(link, client):
                    if link.source == "mercadolivre":
                        return ml_parser.parse(link, client)
                    else:
                        logging.warning(f"Source desconhecida: {link.source}")
                        return None
                
                # Processar links em paralelo
                items = link_parser.parse_links_parallel(pending_links, parse_link)
                logging.info(f"Parse concluído. Itens parseados: {len(items)}")
            else:
                items = []
                logging.info("Nenhum link pendente para processar.")

            # 4) Processamento/Persistência (estrutura de ofertas)
            logging.info("Fase 4: Processando itens (persistência/estrutura de ofertas)…")
            processor = OfferProcessor(self.db)
            for it in items:
                processor.process_item(it)
            logging.info(f"Processamento concluído. Stats: {processor.stats}")

            # 5) Validação — mantém sua lógica atual
            logging.info("Fase 5: Iniciando validação…")
            validator = Validator(self.db)
            validator.run_validation()
            logging.info("Validação concluída.")

            # 6) Publicação — mantém sua lógica atual
            logging.info("Fase 6: Iniciando publicação…")
            publisher = Publisher(self.db)
            publisher.run_publication()
            logging.info("Publicação concluída.")

            # 7) Métricas — mantém sua lógica atual
            logging.info("Fase 7: Iniciando análise de métricas…")
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
