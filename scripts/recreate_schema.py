import os
import sys
import json
import pathlib
from datetime import datetime
from sqlalchemy.inspection import inspect

# Descobre paths
SCRIPT_PATH = pathlib.Path(__file__).resolve()
BACKEND_PATH = SCRIPT_PATH.parents[1]          # .../curadoria_ofertas/backend
PROJECT_ROOT = BACKEND_PATH.parent             # .../curadoria_ofertas

# Injeta no sys.path (prioridade)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

def _try_imports():
    errs = []
    # Tentativas ordenadas
    candidates = [
        ("backend.db.database", "db.database"),
        ("backend.database", "database"),
    ]
    engine = SessionLocal = Base = models_module = None
    for full_mod, short_hint in candidates:
        try:
            if full_mod == "backend.db.database":
                from backend.db.database import SessionLocal, engine  # type: ignore
            elif full_mod == "backend.database":
                from backend.database import SessionLocal, engine  # type: ignore
            # Base e models
            try:
                from backend.models.models import Base  # type: ignore
                from backend.models import models as models_module  # type: ignore
            except Exception:
                from models.models import Base  # type: ignore
                from models import models as models_module  # type: ignore
            return SessionLocal, engine, Base, models_module, errs
        except Exception as e:
            errs.append(f"Falha import {full_mod}: {e}")
    # Última tentativa relativa
    try:
        from db.database import SessionLocal, engine  # type: ignore
        from models.models import Base  # type: ignore
        from models import models as models_module  # type: ignore
        return SessionLocal, engine, Base, models_module, errs
    except Exception as e:
        errs.append(f"Falha import relativo final: {e}")
        return None, None, None, None, errs

SessionLocal, engine, Base, models_module, import_errors = _try_imports()
if not all([SessionLocal, engine, Base, models_module]):
    print("[recreate_schema] ERRO: Não foi possível importar módulos.")
    print("Tentativas:")
    for er in import_errors:
        print(" -", er)
    print("Verifique:")
    print("1. Estrutura de pastas (ex: backend/db/database.py)")
    print("2. Presença de __init__.py nas pastas (crie arquivos vazios).")
    print("3. Execute a partir da raiz: python -m backend.scripts.recreate_schema")
    sys.exit(1)

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups_schema")
os.makedirs(BACKUP_DIR, exist_ok=True)

def serialize_instance(obj):
    mapper = inspect(obj).mapper
    data = {}
    for col in mapper.columns:
        val = getattr(obj, col.key)
        if isinstance(val, datetime):
            val = val.isoformat()
        data[col.key] = val
    return data

def backup_all(session):
    print("[recreate_schema] Iniciando backup...")
    for attr in dir(models_module):
        cls = getattr(models_module, attr)
        if not hasattr(cls, "__table__") or not hasattr(cls, "__tablename__"):
            continue
        try:
            rows = session.query(cls).all()
        except Exception:
            continue
        if not rows:
            continue
        data = [serialize_instance(r) for r in rows]
        fname = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{cls.__tablename__}.json"
        with open(os.path.join(BACKUP_DIR, fname), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[recreate_schema] Backup {cls.__tablename__}: {len(rows)} registros -> {fname}")
    print("[recreate_schema] Backup concluído.")

def drop_and_create():
    print("[recreate_schema] Dropando tabelas...")
    Base.metadata.drop_all(bind=engine)
    print("[recreate_schema] Recriando tabelas...")
    Base.metadata.create_all(bind=engine)
    print("[recreate_schema] OK.")

def main(confirm=True):
    if confirm:
        resp = input("ATENÇÃO: DROP & CREATE em TODO o schema. Digite 'SIM' para continuar: ")
        if resp.strip().upper() != "SIM":
            print("Abortado.")
            return
    session = SessionLocal()
    try:
        backup_all(session)
    finally:
        session.close()
    drop_and_create()

if __name__ == "__main__":
    main()