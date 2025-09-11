from backend.db.database import SessionLocal
from backend.models.models import ConfigVar

with SessionLocal() as db:
    db.query(ConfigVar).filter(ConfigVar.key == "BITLY_API_KEY").delete(synchronize_session=False)
    db.commit()
print("ConfigVar BITLY_API_KEY removido, se existia.")