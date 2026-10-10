"""Carrega a gold publicada (outputs/*.parquet, versionada no Git) no schema gold do warehouse local.

Para a máquina que não roda o pipeline (não tem os arquivos brutos do INEP): outro dev roda o pipeline, faz push de
outputs/, e aqui basta `git pull` + `.\\scripts\\dh.ps1 carregar-gold`. Equivale ao deploy/superset/load_gold.py da Railway.

Tudo numa única transação: quem lê (Superset, chat) vê a gold anterior inteira ou a nova inteira, nunca uma tabela pela metade.
Tabelas do schema gold que não têm parquet em outputs/ ficam como estão.
Roda dentro da imagem CLI (psycopg + pyarrow); usa WAREHOUSE_ADMIN_USER/WAREHOUSE_ADMIN_PASSWORD.
"""
import os
import sys
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from psycopg import sql

OUTPUTS = Path(os.environ.get("OUTPUTS_DIR", "/opt/datahack/outputs"))
BI_USER = os.environ.get("WAREHOUSE_BI_USER", "dh_bi_reader")


def pg_type(t: pa.DataType) -> str:
    if pa.types.is_boolean(t):
        return "boolean"
    if pa.types.is_integer(t):
        return "bigint"
    if pa.types.is_floating(t):
        return "double precision"
    if pa.types.is_decimal(t):
        return f"numeric({t.precision},{t.scale})"
    if pa.types.is_date(t):
        return "date"
    if pa.types.is_timestamp(t):
        return "timestamp with time zone" if t.tz else "timestamp"
    return "text"


def main() -> int:
    files = sorted(p for p in OUTPUTS.glob("*.parquet") if not p.name.startswith("_"))
    if not files:
        print(f">> carregar-gold: nenhum .parquet em {OUTPUTS} (faça git pull dos outputs/ primeiro)")
        return 1
    conninfo = dict(
        host=os.environ.get("WAREHOUSE_HOST", "warehouse"), port=os.environ.get("WAREHOUSE_PORT", "5432"),
        dbname=os.environ.get("WAREHOUSE_DB", "datahack"),
        user=os.environ.get("WAREHOUSE_ADMIN_USER", "dh_admin"), password=os.environ["WAREHOUSE_ADMIN_PASSWORD"],
    )
    with psycopg.connect(**conninfo) as conn:       # sair do with sem erro = commit; com erro = rollback de tudo
        conn.execute("CREATE SCHEMA IF NOT EXISTS gold")
        for path in files:
            table = pq.read_table(path)
            ident = sql.Identifier("gold", path.stem)
            cols = [sql.Identifier(f.name) for f in table.schema]
            ddl = sql.SQL("CREATE TABLE {} ({})").format(
                ident, sql.SQL(", ").join(sql.SQL("{} {}").format(c, sql.SQL(pg_type(f.type))) for c, f in zip(cols, table.schema)))
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(ident))
            conn.execute(ddl)
            with conn.cursor() as cur, cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(ident, sql.SQL(", ").join(cols))) as copy:
                for row in zip(*(table.column(i).to_pylist() for i in range(table.num_columns))):
                    copy.write_row(row)
            print(f">> gold.{path.stem}: {table.num_rows} linhas")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA gold TO {}").format(sql.Identifier(BI_USER)))
        conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA gold TO {}").format(sql.Identifier(BI_USER)))
    print(">> carregar-gold: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
