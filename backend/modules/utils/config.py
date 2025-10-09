# backend/utils/config.py
import os
from datetime import datetime
from backend.db.database import SessionLocal
from backend.models.models import ConfigVar

def get_config(key: str, default: str | None = None) -> str | None:
    with SessionLocal() as db:
        row = db.query(ConfigVar).filter(ConfigVar.key == key).first()
        if row and row.value is not None:
            return row.value
    return os.getenv(key, default)

def set_config(key: str, value: str | None, is_secret: bool = True, description: str | None = None):
    with SessionLocal() as db:
        row = db.query(ConfigVar).filter(ConfigVar.key == key).first()
        if not row:
            row = ConfigVar(key=key)
            db.add(row)
        row.value = value
        row.is_secret = is_secret
        if description is not None:
            row.description = description
        row.updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        return row

def list_configs():
    with SessionLocal() as db:
        return db.query(ConfigVar).order_by(ConfigVar.key.asc()).all()
