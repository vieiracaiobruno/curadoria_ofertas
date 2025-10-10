#!/usr/bin/env python3
"""
Script para criar/atualizar tabelas do banco de dados.
Executa create_all() que cria apenas as tabelas que não existem.
"""
import sys
import os

# Adiciona o diretório raiz ao path
root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, root)

from backend.db.database import create_db_tables

if __name__ == "__main__":
    print("Criando/atualizando tabelas do banco de dados...")
    create_db_tables()
    print("Tabelas criadas com sucesso!")
    print("\nNOTA: A tabela 'links_coleta' foi adicionada ao modelo.")
    print("Se você estiver usando um banco existente, a tabela foi criada automaticamente.")
