#!/usr/bin/env python3
"""
Pipeline simplificado de curadoria de ofertas
Este script simula a execução do pipeline sem dependências complexas
"""

import os
import sys
import logging
from datetime import datetime
import json

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/pipeline.log'),
        logging.StreamHandler()
    ]
)

def simulate_data_collection():
    """Simula a coleta de dados de ofertas"""
    logging.info("Iniciando coleta de ofertas...")
    
    # Simula ofertas encontradas
    ofertas_simuladas = [
        {
            "id": f"oferta_{datetime.now().strftime('%Y%m%d_%H%M%S')}_1",
            "produto": "Notebook Gamer Acer",
            "preco_original": 2899.99,
            "preco_oferta": 2199.99,
            "desconto": 24.1,
            "loja": "Amazon",
            "url": "https://amazon.com.br/produto/123",
            "categoria": "informatica",
            "data_encontrada": datetime.now().isoformat()
        },
        {
            "id": f"oferta_{datetime.now().strftime('%Y%m%d_%H%M%S')}_2",
            "produto": "Mouse Gamer Logitech",
            "preco_original": 299.99,
            "preco_oferta": 179.99,
            "desconto": 40.0,
            "loja": "Mercado Livre",
            "url": "https://mercadolivre.com.br/produto/456",
            "categoria": "gamer",
            "data_encontrada": datetime.now().isoformat()
        }
    ]
    
    logging.info(f"Encontradas {len(ofertas_simuladas)} ofertas")
    return ofertas_simuladas

def validate_offers(ofertas):
    """Simula a validação de ofertas"""
    logging.info("Iniciando validação de ofertas...")
    
    ofertas_validas = []
    for oferta in ofertas:
        # Simula validação (desconto mínimo de 15%)
        if oferta["desconto"] >= 15:
            oferta["status"] = "APROVADA"
            ofertas_validas.append(oferta)
            logging.info(f"Oferta aprovada: {oferta['produto']} - {oferta['desconto']:.1f}% desconto")
        else:
            oferta["status"] = "REJEITADA"
            logging.info(f"Oferta rejeitada: {oferta['produto']} - desconto insuficiente")
    
    logging.info(f"{len(ofertas_validas)} ofertas aprovadas para publicação")
    return ofertas_validas

def publish_offers(ofertas_validas):
    """Simula a publicação de ofertas"""
    logging.info("Iniciando publicação de ofertas...")
    
    for oferta in ofertas_validas:
        # Simula publicação no Telegram
        logging.info(f"Publicando no Telegram: {oferta['produto']}")
        
        # Simula criação de link encurtado
        link_encurtado = f"https://bit.ly/{oferta['id'][:8]}"
        oferta["link_publicado"] = link_encurtado
        
        # Simula métricas iniciais
        oferta["cliques"] = 0
        oferta["vendas"] = 0
        oferta["data_publicacao"] = datetime.now().isoformat()
    
    logging.info(f"Publicadas {len(ofertas_validas)} ofertas")
    return ofertas_validas

def save_results(ofertas_publicadas):
    """Salva os resultados em arquivo JSON"""
    results_file = "./logs/pipeline_results.json"
    
    # Carrega resultados anteriores se existirem
    try:
        with open(results_file, 'r') as f:
            all_results = json.load(f)
    except FileNotFoundError:
        all_results = []
    
    # Adiciona novos resultados
    execution_result = {
        "timestamp": datetime.now().isoformat(),
        "ofertas_encontradas": len(ofertas_publicadas),
        "ofertas": ofertas_publicadas
    }
    
    all_results.append(execution_result)
    
    # Mantém apenas os últimos 50 resultados
    if len(all_results) > 50:
        all_results = all_results[-50:]
    
    # Salva resultados
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Resultados salvos em {results_file}")

def run_pipeline():
    """Executa o pipeline completo"""
    try:
        logging.info("=== Iniciando Pipeline de Curadoria de Ofertas ===")
        
        # 1. Coleta de dados
        ofertas = simulate_data_collection()
        
        # 2. Validação
        ofertas_validas = validate_offers(ofertas)
        
        # 3. Publicação
        ofertas_publicadas = publish_offers(ofertas_validas)
        
        # 4. Salvar resultados
        save_results(ofertas_publicadas)
        
        logging.info("=== Pipeline executado com sucesso ===")
        
    except Exception as e:
        logging.error(f"Erro durante a execução do pipeline: {e}")
        raise

if __name__ == "__main__":
    run_pipeline()

