import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config.env')

# Configuração do banco de dados SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend/db/curadoria_ofertas.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Tabelas de ligação N:N
produto_tags_association = Table(
    'produto_tags',
    Base.metadata,
    Column('produto_id', Integer, ForeignKey('produtos.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

canal_tags_association = Table(
    'canal_tags',
    Base.metadata,
    Column('canal_id', Integer, ForeignKey('canais_telegram.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

# Função para criar as tabelas no banco de dados
def create_db_tables():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    create_db_tables()
    print("Tabelas do banco de dados criadas com sucesso!")