import json
import argparse
from datetime import datetime
from pathlib import Path
import sys

# Garante que o diretório raiz do projeto está no sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Importa Base, engine e SessionLocal do projeto
from backend.db.database import Base, engine, SessionLocal  # ajuste se necessário
# Garante que TODOS os modelos estejam registrados no metadata antes de create_all
import backend.models.models as models  # noqa: F401
from backend.models.models import ConfigVar, Tag, CanalTelegram

from sqlalchemy import Table  # para checar tabelas de associação


def _row_to_dict(row):
    """Converte uma instância ORM em dict baseado nas colunas da tabela."""
    data = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, datetime):
            data[col.name] = val.isoformat()
        else:
            data[col.name] = val
    return data


def backup_table(session, model, out_file: Path) -> int:
    """Backup genérico de uma tabela ORM (apenas colunas, ignora relacionamentos)."""
    rows = session.query(model).all()
    payload = [_row_to_dict(r) for r in rows]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Backup [{model.__tablename__}] salvo: {out_file} ({len(payload)} registros)")
    return len(payload)


def backup_association_table(table: Table, out_file: Path) -> int:
    """Backup de tabela de associação (sqlalchemy.Table)."""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    conn = engine.connect()
    try:
        sel = table.select()
        result = conn.execute(sel)
        rows = [dict(r) for r in result.fetchall()]
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"Backup [assoc:{table.name}] salvo: {out_file} ({len(rows)} registros)")
        return len(rows)
    finally:
        conn.close()


def restore_table(session, model, in_file: Path) -> int:
    """Restaura uma tabela a partir de JSON (apenas colunas, ignora relacionamentos)."""
    if not in_file.exists():
        print(f"Nenhum arquivo de backup encontrado para {model.__tablename__} em {in_file}")
        return 0
    with in_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    restored = 0
    for row in data:
        # Inserção direta preservando IDs se presentes
        obj = model(**row)
        session.add(obj)
        restored += 1
    session.commit()
    print(f"Restauração [{model.__tablename__}] concluída: {restored} registros")
    return restored


def restore_association_table(table: Table, in_file: Path) -> int:
    """Restaura uma tabela de associação a partir de JSON (insere linhas brutas)."""
    if not in_file.exists():
        print(f"Nenhum arquivo de backup encontrado para assoc:{table.name} em {in_file}")
        return 0
    with in_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        print(f"Nenhum registro para restaurar em assoc:{table.name}")
        return 0
    conn = engine.connect()
    trans = conn.begin()
    try:
        # Insere todas as linhas; espera-se que os campos batam com as colunas
        conn.execute(table.insert(), data)
        trans.commit()
        print(f"Restauração [assoc:{table.name}] concluída: {len(data)} registros")
        return len(data)
    except Exception as e:
        trans.rollback()
        print(f"Erro ao restaurar assoc:{table.name}: {e}")
        raise
    finally:
        conn.close()


def backup_config_vars(session, out_file: Path) -> int:
    # Mantém versão específica (trata datetime)
    rows = session.query(ConfigVar).all()
    payload = []
    for r in rows:
        payload.append({
            "key": r.key,
            "value": r.value,
            "is_secret": bool(r.is_secret),
            "description": r.description,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Backup [config_vars] salvo: {out_file} ({len(payload)} registros)")
    return len(payload)


def drop_all():
    print("Derrubando todas as tabelas...")
    Base.metadata.drop_all(bind=engine)
    print("Tabelas removidas.")


def create_all():
    print("Recriando todas as tabelas...")
    Base.metadata.create_all(bind=engine)
    print("Tabelas recriadas.")


def restore_config_vars(session, in_file: Path) -> int:
    if not in_file.exists():
        print(f"Nenhum arquivo de backup encontrado em {in_file}")
        return 0
    with in_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    restored = 0
    for row in data:
        updated_at = None
        if row.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(row["updated_at"])
            except Exception:
                updated_at = datetime.now()
        cv = ConfigVar(
            key=row.get("key"),
            value=row.get("value"),
            is_secret=bool(row.get("is_secret", True)),
            description=row.get("description"),
            updated_at=updated_at or datetime.now(),
        )
        session.add(cv)
        restored += 1
    session.commit()
    print(f"Restauração [config_vars] concluída: {restored} registros")
    return restored


def main():
    parser = argparse.ArgumentParser(
        description="Backup de config_vars, tags, canais_telegram e tabelas de associação; reset total do schema; restore dos backups."
    )
    parser.add_argument("--backup-dir", help="Diretório para salvar/ler backups (opcional).")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    # Por padrão gravar backups em backend/scripts/backups_db
    backups_dir = Path(args.backup_dir) if args.backup_dir else (project_root / "backend" / "scripts" / "backups_db")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    cfg_backup = backups_dir / f"config_vars_backup_{timestamp}.json"
    tags_backup = backups_dir / f"tags_backup_{timestamp}.json"
    canais_backup = backups_dir / f"canais_telegram_backup_{timestamp}.json"
    produto_tags_backup = backups_dir / f"produto_tags_backup_{timestamp}.json"
    canal_tags_backup = backups_dir / f"canal_tags_backup_{timestamp}.json"

    # Resolve objetos de associação se existirem no módulo models
    produto_tags_table = getattr(models, "produto_tags", None)
    canal_tags_table = getattr(models, "canal_tags", None)

    # 1) Backup: config_vars, tags, canais_telegram, produto_tags, canal_tags
    with SessionLocal() as session:
        backup_config_vars(session, cfg_backup)
        backup_table(session, Tag, tags_backup)
        backup_table(session, CanalTelegram, canais_backup)

        if produto_tags_table is not None:
            try:
                backup_association_table(produto_tags_table, produto_tags_backup)
            except Exception as e:
                print(f"Falha ao fazer backup produto_tags: {e}")
        else:
            print("Tabela de associação 'produto_tags' não encontrada nos modelos; pulando backup.")

        if canal_tags_table is not None:
            try:
                backup_association_table(canal_tags_table, canal_tags_backup)
            except Exception as e:
                print(f"Falha ao fazer backup canal_tags: {e}")
        else:
            print("Tabela de associação 'canal_tags' não encontrada nos modelos; pulando backup.")

    # 2) Drop all
    drop_all()

    # 3) Create all
    create_all()

    # 4) Restore na ordem: config_vars -> tags -> canais_telegram -> produto_tags -> canal_tags
    with SessionLocal() as session:
        restore_config_vars(session, cfg_backup)
        restore_table(session, Tag, tags_backup)
        restore_table(session, CanalTelegram, canais_backup)

    # Restaurar associações usando conexão direta (após criar todas as tabelas)
    if produto_tags_table is not None:
        try:
            restore_association_table(produto_tags_table, produto_tags_backup)
        except Exception as e:
            print(f"Falha ao restaurar produto_tags: {e}")
    else:
        print("Tabela de associação 'produto_tags' não encontrada; pulando restore.")

    if canal_tags_table is not None:
        try:
            restore_association_table(canal_tags_table, canal_tags_backup)
        except Exception as e:
            print(f"Falha ao restaurar canal_tags: {e}")
    else:
        print("Tabela de associação 'canal_tags' não encontrada; pulando restore.")

    print("Processo concluído com sucesso.")


if __name__ == "__main__":
    main()