import sqlite3
from pathlib import Path
import shutil
import sys

DB_PATH = Path("backend/db/curadoria_ofertas.db")

SQL_MIGRATION = """
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;
ALTER TABLE produtos RENAME TO produtos_old;
CREATE TABLE produtos (
  id INTEGER PRIMARY KEY,
  id_product TEXT NOT NULL UNIQUE,
  product_id_loja TEXT NOT NULL,
  product_id_loja_alt TEXT,
  nome_produto TEXT NOT NULL,
  url_base TEXT NOT NULL,
  imagem_url TEXT
);
INSERT INTO produtos (id,id_product,product_id_loja,product_id_loja_alt,nome_produto,url_base,imagem_url)
  SELECT id,id_product,product_id_loja,product_id_loja_alt,nome_produto,url_base,imagem_url FROM produtos_old;
CREATE INDEX ix_produtos_product_id_loja ON produtos(product_id_loja);
CREATE INDEX ix_produtos_product_id_loja_alt ON produtos(product_id_loja_alt);
CREATE INDEX ix_produtos_id_product ON produtos(id_product);
COMMIT;
PRAGMA foreign_keys=on;
DROP TABLE produtos_old;
"""

def table_has_column(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())

def already_migrated(conn):
    if not table_has_column(conn, "produtos", "id_product"):
        return False
    # Check uniqueness removal: try to create duplicate index test (light heuristic)
    return True

def main():
    if not DB_PATH.exists():
        print(f"[ERRO] Banco não encontrado: {DB_PATH}")
        sys.exit(1)

    backup = DB_PATH.with_suffix(".backup.db")
    if not backup.exists():
        shutil.copyfile(DB_PATH, backup)
        print(f"[INFO] Backup criado: {backup}")
    else:
        print(f"[INFO] Backup já existe: {backup}")

    conn = sqlite3.connect(DB_PATH)
    try:
        if already_migrated(conn):
            print("[INFO] Migração já aplicada (coluna id_product presente).")
            return
        print("[INFO] Executando migração...")
        conn.executescript(SQL_MIGRATION)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
        print(f"[SUCESSO] Migração concluída. Registros: {count}")
    except Exception as e:
        conn.rollback()
        print("[ERRO] Falha na migração:", e)
        print("[INFO] Restaure o backup se necessário.")
        sys.exit(2)
    finally:
        conn.close()

if __name__ == "__main__":
    main()