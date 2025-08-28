import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config.env')

# Configuração do banco de dados SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend/db/curadoria_ofertas.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Uma ÚNICA Base para todo o projeto
Base = declarative_base()

def create_db_tables() -> None:
    """Cria as tabelas no banco.
    IMPORTANTE: garante que os modelos sejam importados UMA vez antes do create_all.
    """
    # Import tardio para registrar todos os modelos nesta Base
    try:
        # Ajuste este import conforme o seu pacote real
        import backend.models.models  # noqa: F401
    except Exception:
        # Fallback para execuções fora do pacote (ex.: scripts locais)
        try:
            import models  # noqa: F401
        except Exception:
            pass
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    create_db_tables()
    print("Tabelas do banco de dados criadas com sucesso!")