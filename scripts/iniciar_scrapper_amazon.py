#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script standalone para demonstrar o uso do AmazonCollector.
Similar ao iniciar_scrapper_ml.py, mas para Amazon.

Uso:
    python scripts/iniciar_scrapper_amazon.py
"""
import os
import sys
import logging

# Adicionar o diretório raiz ao path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from backend.modules.collectors.amazon_collector import AmazonCollector
from backend.modules.utils.config import get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def main():
    """
    Executa a coleta de ofertas da Amazon e exibe os resultados.
    """
    logging.info("=== Iniciando coleta da Amazon ===")
    
    # Obter configurações do perfil do Chrome
    user_data_dir = get_config("SELENIUM_USER_DATA_DIR", "")
    profile_dir = get_config("SELENIUM_PROFILE_DIR", "")
    
    # Criar instância do coletor
    collector = AmazonCollector(
        user_data_dir=user_data_dir,
        profile_dir=profile_dir,
        detach=False,
    )
    
    try:
        # Executar coleta
        items = collector.run_collection()
        
        logging.info(f"\n=== Coleta finalizada ===")
        logging.info(f"Total de produtos coletados: {len(items)}")
        
        # Exibir resumo dos primeiros itens
        if items:
            logging.info("\n=== Primeiros produtos coletados ===")
            for i, item in enumerate(items[:5], 1):
                logging.info(f"\nProduto {i}:")
                logging.info(f"  Nome: {item.get('nome_produto', 'N/A')}")
                logging.info(f"  Preço: R$ {item.get('preco_oferta', 'N/A')}")
                logging.info(f"  Desconto: {item.get('desconto', 'N/A')}%")
                logging.info(f"  Loja: {item.get('store_name', 'N/A')}")
                logging.info(f"  URL: {item.get('url_base', 'N/A')}")
            
            if len(items) > 5:
                logging.info(f"\n... e mais {len(items) - 5} produtos.")
        else:
            logging.warning("Nenhum produto foi coletado. Verifique as configurações.")
        
    except Exception as e:
        logging.exception(f"Erro durante a coleta: {e}")
        raise
    finally:
        collector.close()


if __name__ == "__main__":
    main()
