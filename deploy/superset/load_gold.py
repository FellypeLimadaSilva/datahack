"""Prepara o Postgres da Railway e carrega a gold publicada (outputs/*.parquet) antes do Superset subir.

Idempotente: pode rodar a cada deploy. O que faz, com o usuário administrador do plugin Postgres (PGHOST/PGUSER/...):
  1. cria os databases `datahack` (warehouse) e `superset` (metadados do Superset), se faltarem;
  2. cria/atualiza o papel somente leitura dh_bi_reader (mesmas travas do infra/postgres/bootstrap.sql);
  3. recarrega o schema gold numa única transação (quem lê nunca vê tabela pela metade) e libera SELECT ao dh_bi_reader.
Substitui o bootstrap.sql/pipeline do laboratório: na nuvem não há os arquivos brutos do INEP, só o resultado em outputs/.
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

OUTPUTS = Path(os.environ.get("OUTPUTS_DIR", "/app/outputs"))
WAREHOUSE_DB = os.environ.get("WAREHOUSE_DB", "datahack")
SUPERSET_DB = os.environ.get("SUPERSET_DB_NAME", "superset")
BI_USER = os.environ.get("WAREHOUSE_BI_USER", "dh_bi_reader")
ADMIN = dict(
    host=os.environ["PGHOST"], port=os.environ.get("PGPORT", "5432"),
    user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
)
ADMIN_DB = os.environ.get("PGDATABASE", "railway")


def connect(dbname: str):
    last = None
    for _ in range(30):                       # o Postgres pode estar subindo junto
        try:
            return psycopg2.connect(dbname=dbname, connect_timeout=5, **ADMIN)
        except psycopg2.OperationalError as exc:
            last = exc
            time.sleep(4)
    raise SystemExit(f">> load_gold: sem conexão com o Postgres: {last}")


def ensure_databases() -> None:
    con = connect(ADMIN_DB)
    con.autocommit = True
    with con.cursor() as cur:
        for name in (WAREHOUSE_DB, SUPERSET_DB):
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                print(f">> database criado: {name}")
        cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(SUPERSET_DB)))   # o BI não precisa dos metadados
        password = os.environ.get("WAREHOUSE_BI_PASSWORD")
        if not password:
            raise SystemExit(">> load_gold: defina WAREHOUSE_BI_PASSWORD (senha que o dh_bi_reader vai ter)")
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (BI_USER,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(BI_USER)))
        cur.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
                    "PASSWORD {} CONNECTION LIMIT 20").format(sql.Identifier(BI_USER), sql.Literal(password)))
        for setting, value in (("default_transaction_read_only", "on"), ("statement_timeout", "120s"),
                               ("idle_in_transaction_session_timeout", "60s"), ("search_path", "gold")):
            cur.execute(sql.SQL("ALTER ROLE {} SET {} = {}").format(
                sql.Identifier(BI_USER), sql.Identifier(setting), sql.Literal(value)))
        cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(WAREHOUSE_DB)))
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(WAREHOUSE_DB), sql.Identifier(BI_USER)))
    con.close()


def load_gold() -> None:
    files = sorted(p for p in OUTPUTS.glob("*.parquet") if not p.name.startswith("_"))
    if not files:
        raise SystemExit(f">> load_gold: nenhum .parquet em {OUTPUTS} (a gold do repositório está vazia?)")
    engine = create_engine(URL.create(
        "postgresql+psycopg2", username=ADMIN["user"], password=ADMIN["password"],
        host=ADMIN["host"], port=int(ADMIN["port"]), database=WAREHOUSE_DB))
    with engine.begin() as conn:               # uma transação: ou a gold nova inteira, ou a anterior intacta
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold"))
        for path in files:
            frame = pd.read_parquet(path)
            frame.to_sql(path.stem, conn, schema="gold", if_exists="replace", index=False, chunksize=5000, method="multi")
            print(f">> gold.{path.stem}: {len(frame)} linhas")
        conn.execute(text("REVOKE ALL ON SCHEMA gold FROM PUBLIC"))
        conn.execute(text(f'GRANT USAGE ON SCHEMA gold TO "{BI_USER}"'))
        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA gold TO "{BI_USER}"'))
        conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO "{BI_USER}"'))
    engine.dispose()


if __name__ == "__main__":
    ensure_databases()
    load_gold()
    print(">> load_gold: ok")
    sys.stdout.flush()
