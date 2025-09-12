#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RunPipeline (classe) — orquestra a curadoria de ofertas seguindo o modelo do run_pipeline.py,
mas usando a coleta simples (requests + BeautifulSoup) como base.
"""
import os
import logging
import sys

project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# DB
try:
    from backend.db.database import SessionLocal
except Exception:
    from db.database import SessionLocal  # fallback

# Módulos
try:
    from backend.modules.collector import Collector
except Exception:
    from modules.collector import Collector  # fallback

try:
    from backend.modules.validator import Validator
except Exception:
    from modules.validator import Validator  # fallback

try:
    from backend.modules.publisher import Publisher
except Exception:
    from modules.publisher import Publisher  # fallback

try:
    from backend.modules.metrics_analyzer import MetricsAnalyzer
except Exception:
    from modules.metrics_analyzer import MetricsAnalyzer  # fallback


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

            # 1) Coleta (requests+BS4) — baseado no run_pipeline_simple.py
            logging.info("Iniciando coleta (Collector - requests/BS4)…")
            collector = Collector(self.db)
            collector.run_collection()
            logging.info("Coleta concluída.")

            # 2) Validação — mantém sua lógica atual
            logging.info("Iniciando validação…")
            validator = Validator(self.db)
            validator.run_validation()
            logging.info("Validação concluída.")

            # 3) Publicação — mantém sua lógica atual
            logging.info("Iniciando publicação…")
            publisher = Publisher(self.db)
            publisher.run_publication()
            logging.info("Publicação concluída.")

            # 4) Métricas — mantém sua lógica atual
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
