"""
Remove TODOS os registros das tabelas (dados operacionais) preservando:

  - usuarios          (tabela: usuarios)
  - canais_telegram   (tabela: canais_telegram)
  - tags              (tabela: tags)
  - canal_tags        (tabela de ligação: canal_tags)
  - config_vars       (tabela: config_vars)

Apaga (se existirem):
  produtos, produto_tags, lojas_confiaveis, historico_precos, ofertas,
  metricas_ofertas, ofertas_publicadas, logs_coleta

Uso:
    python backend/scripts/clear_data_preserve_core.py

Recomenda-se BACKUP antes:
    copy backend\\db\\curadoria_ofertas.db backend\\db\\curadoria_ofertas.backup.db
"""

import sys
from pathlib import Path
import sqlite3

DB_PATHS_CANDIDATES = [
    "backend/db/curadoria_ofertas.db",
    "backend/db/database.db",
    "backend/db/app.db",
]

PRESERVAR = {
    "usuarios",
    "canais_telegram",
    "tags",
    "canal_tags",
    "config_vars",
}

# Ordem para excluir respeitando FKs (filhos antes de pais)
APAGAR_ORDEM = [
    "metricas_ofertas",
    "ofertas_publicadas",
    "historico_precos",
    "produto_tags",
    "ofertas",
    "logs_coleta",
    "produtos",
    "lojas_confiaveis",
]

def detectar_db():
    for p in DB_PATHS_CANDIDATES:
        if Path(p).exists():
            return p
    # fallback primeiro .db
    for p in Path("backend/db").glob("*.db"):
        return str(p)
    return None

def listar_tabelas(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return {r[0] for r in cur.fetchall()}

def limpar():
    db_path = detectar_db()
    if not db_path:
        print("[ERRO] Não foi encontrado arquivo .db em backend/db.")
        return 1

    print(f"[INFO] Usando banco: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA foreign_keys=OFF;")
        conn.commit()

        existentes = listar_tabelas(conn)

        # Ajusta lista real de apagar para só tabelas existentes e não preservadas
        apagar = [t for t in APAGAR_ORDEM if t in existentes and t not in PRESERVAR]

        print("[INFO] Tabelas preservadas:", ", ".join(sorted(PRESERVAR.intersection(existentes))) or "(nenhuma encontrada)")
        print("[INFO] Tabelas a limpar:", ", ".join(apagar) or "(nenhuma)")

        for tabela in apagar:
            try:
                cur.execute(f"DELETE FROM {tabela};")
                conn.commit()
                print(f"[OK] Limpeza: {tabela}")
            except Exception as e_t:
                conn.rollback()
                print(f"[ERRO] Falha ao limpar {tabela}: {e_t}")

        print("[INFO] Concluído.")
        return 0
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    sys.exit(limpar())
