import os
import re
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect

# Ajuste dinâmica de paths
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (ROOT, BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

# Imports dinâmicos (ajuste conforme sua estrutura real)
def load_env():
    import importlib
    errors = []
    targets = [
        ("backend.db.database", "backend.models.models"),
        ("backend.database", "backend.models.models"),
        ("db.database", "models.models"),
    ]
    for db_mod, models_mod in targets:
        try:
            dbm = importlib.import_module(db_mod)
            mm = importlib.import_module(models_mod)
            Base = getattr(mm, "Base", None)
            if not Base:
                # Algumas estruturas definem Base no database
                Base = getattr(dbm, "Base", None)
            SessionLocal = getattr(dbm, "SessionLocal", None)
            engine = getattr(dbm, "engine", None)
            if all([Base, SessionLocal, engine]):
                return Base, SessionLocal, engine, mm
        except Exception as e:
            errors.append(f"Tentativa {db_mod} -> {e}")
    print("[restore_backups] Falha imports. Tentativas:")
    for e in errors:
        print(" -", e)
    sys.exit(1)

Base, SessionLocal, engine, models_module = load_env()

TIMESTAMP_PREFIX_RE = re.compile(r"^\d{8}_\d{6}_")  # 20250915_015848_

def infer_table_name(filename: str) -> str:
    name = os.path.splitext(os.path.basename(filename))[0]
    return TIMESTAMP_PREFIX_RE.sub("", name)

def find_model_by_tablename(tablename: str):
    for attr in dir(models_module):
        cls = getattr(models_module, attr)
        if hasattr(cls, "__tablename__") and getattr(cls, "__tablename__") == tablename:
            return cls
    return None

def parse_datetime(val: str):
    # Aceita ISO; se falhar retorna original
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return val

def coerce_types(cls, row: Dict[str, Any]):
    mapper = inspect(cls)
    for col in mapper.columns:
        key = col.key
        if key not in row:
            continue
        val = row[key]
        if val is None:
            continue
        # Datetime
        if hasattr(col.type, "python_type"):
            pytype = None
            try:
                pytype = col.type.python_type
            except Exception:
                pass
            if pytype is datetime and isinstance(val, str):
                row[key] = parse_datetime(val)
    return row

def ordered_tables(all_files: Dict[str, str]) -> List[str]:
    # Ordem manual para dependências (ajuste conforme seu schema)
    preferred = [
        "usuarios",
        "canais_telegram",
        "lojas_confiaveis",
        "produtos",
        "tags",
        # tabelas de associação se existirem depois
        "logs_coleta",
        "config_vars",
    ]
    present = set(all_files.keys())
    ordered = [t for t in preferred if t in present]
    # Restantes não listados
    for t in sorted(present):
        if t not in ordered:
            ordered.append(t)
    return ordered

def reset_postgres_sequences(session):
    # Apenas se PostgreSQL
    if session.bind.dialect.name != "postgresql":
        return
    print("[restore_backups] Ajustando sequences (PostgreSQL)...")
    for cls in Base.__subclasses__():
        if not hasattr(cls, "__tablename__"):
            continue
        insp = inspect(cls)
        pks = insp.primary_key
        if len(pks) != 1:
            continue
        pk_col = pks[0]
        if pk_col.autoincrement is True:
            table = cls.__tablename__
            pk_name = pk_col.key
            try:
                max_id = session.execute(f'SELECT MAX("{pk_name}") FROM "{table}"').scalar()
                if max_id is not None:
                    seq_name = f"{table}_{pk_name}_seq"
                    session.execute(f"SELECT setval('{seq_name}', {int(max_id)}, true)")
            except Exception as e:
                print(f"[restore_backups] Aviso: não ajustou sequence {table}: {e}")
    session.commit()

def load_json_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def restore_table(session, tablename: str, filepath: str, mode: str, dry_run: bool):
    model = find_model_by_tablename(tablename)
    if not model:
        print(f"[restore_backups] Ignorando (modelo não encontrado): {tablename}")
        return {"table": tablename, "status": "skip_no_model"}

    data = load_json_file(filepath)
    if not isinstance(data, list):
        print(f"[restore_backups] Formato inválido em {filepath}")
        return {"table": tablename, "status": "error_format"}
    if not data:
        print(f"[restore_backups] Vazio: {tablename}")
        return {"table": tablename, "status": "empty"}

    mapper = inspect(model)
    pk_cols = [c.key for c in mapper.primary_key]

    inserted = 0
    updated = 0
    skipped = 0
    errors = 0

    print(f"[restore_backups] Restaurando {tablename}: {len(data)} registros (modo={mode})")

    if mode == "insert":
        objs = []
        for row in data:
            row = coerce_types(model, row)
            obj = model(**row)
            objs.append(obj)
        if dry_run:
            print(f"[restore_backups] (dry-run) Inseriria {len(objs)} registros em {tablename}")
            return {"table": tablename, "status": "dry_run", "count": len(objs)}
        try:
            session.bulk_save_objects(objs)
            inserted = len(objs)
        except IntegrityError as e:
            session.rollback()
            print(f"[restore_backups] Falha bulk em {tablename}, revertendo para inserts individuais: {e}")
            for row in data:
                row = coerce_types(model, row)
                try:
                    obj = model(**row)
                    session.add(obj)
                    session.flush()
                    inserted += 1
                except IntegrityError:
                    session.rollback()
                    skipped += 1
                except Exception as ex:
                    session.rollback()
                    errors += 1
                    print(f"[restore_backups] Erro linha {tablename}: {ex}")
        session.commit()
    else:
        # upsert ou skip-existing
        for row in data:
            row = coerce_types(model, row)
            pk_filter = {}
            for pk in pk_cols:
                if pk not in row:
                    pk_filter = None
                    break
                pk_filter[pk] = row[pk]

            existing = None
            if pk_filter:
                try:
                    existing = session.query(model).filter_by(**pk_filter).one_or_none()
                except Exception:
                    existing = None

            if existing:
                if mode == "skip-existing":
                    skipped += 1
                    continue
                elif mode == "upsert":
                    # Atualiza campo a campo
                    for k, v in row.items():
                        setattr(existing, k, v)
                    updated += 1
                continue
            # Não existe
            if dry_run:
                inserted += 1
                continue
            try:
                obj = model(**row)
                session.add(obj)
                session.flush()
                inserted += 1
            except IntegrityError:
                session.rollback()
                skipped += 1
            except Exception as e:
                session.rollback()
                errors += 1
                print(f"[restore_backups] Erro insert {tablename}: {e}")
        if not dry_run:
            session.commit()

    return {
        "table": tablename,
        "status": "ok",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors
    }

def main():
    parser = argparse.ArgumentParser(description="Restaura backups JSON para o banco.")
    parser.add_argument("--dir", default=os.path.join(os.path.dirname(__file__), "backups_schema"), help="Diretório dos JSONs")
    parser.add_argument("--mode", choices=["insert", "upsert", "skip-existing"], default="insert",
                        help="insert=insere bruto; upsert=atualiza se existir; skip-existing=pula existentes")
    parser.add_argument("--tables", nargs="*", help="Lista de tabelas específicas (nomes exatos).")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar.")
    parser.add_argument("--no-seq-fix", action="store_true", help="Não ajustar sequences (PostgreSQL).")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"[restore_backups] Diretório não existe: {args.dir}")
        sys.exit(1)

    # Mapear arquivos
    files = {}
    for fname in os.listdir(args.dir):
        if not fname.endswith(".json"):
            continue
        tablename = infer_table_name(fname)
        files[tablename] = os.path.join(args.dir, fname)

    if not files:
        print("[restore_backups] Nenhum arquivo JSON encontrado.")
        sys.exit(0)

    if args.tables:
        selected = {}
        for t in args.tables:
            if t in files:
                selected[t] = files[t]
            else:
                print(f"[restore_backups] Aviso: tabela {t} não encontrada nos backups.")
        files = selected

    order = ordered_tables(files)
    session = SessionLocal()
    summary = []
    try:
        for t in order:
            res = restore_table(session, t, files[t], args.mode, args.dry_run)
            summary.append(res)
        if not args.dry_run and not args.no_seq_fix:
            try:
                reset_postgres_sequences(session)
            except Exception as e:
                print(f"[restore_backups] Aviso seq: {e}")
    finally:
        session.close()

    print("\n[restore_backups] Resumo:")
    for r in summary:
        print(r)

if __name__ == "__main__":
    main()