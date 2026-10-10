from __future__ import annotations

import hashlib
import logging

import pandas as pd
import psycopg
from psycopg import sql

from datahack_ingest.normalize import row_hash

log = logging.getLogger(__name__)

META_COLUMNS = ("_dh_batch_id", "_dh_ingested_at", "_dh_source_file", "_dh_row_hash")


def _index_name(table: str, suffix: str) -> str:
    name = f"{table}_{suffix}"
    if len(name) <= 63:
        return name
    digest = hashlib.md5(name.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{table[: 63 - len(suffix) - 10]}_{digest}_{suffix}"


class PostgresSink:
    def __init__(
        self,
        conn: psycopg.Connection,
        source_name: str,
        table: str,
        run_id: str,
        schema: str = "bronze",
    ) -> None:
        self.conn = conn
        self.source_name = source_name
        self.schema = schema
        self.table = table
        self.run_id = run_id
        self.target = sql.Identifier(schema, table)
        self._columns: list[str] | None = None
        self.new_columns: list[str] = []

    def prepare(self) -> None:
        self.conn.execute(
            sql.SQL(
                """CREATE TABLE IF NOT EXISTS {t} (
                     _dh_batch_id    uuid        NOT NULL,
                     _dh_ingested_at timestamptz NOT NULL DEFAULT now(),
                     _dh_source_file text,
                     _dh_row_hash    text
                   )"""
            ).format(t=self.target)
        )
        self.conn.execute(
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {i} ON {t} (_dh_source_file, _dh_ingested_at)"
            ).format(i=sql.Identifier(_index_name(self.table, "file_idx")), t=self.target)
        )
        self._columns = self._existing_columns()

    def _existing_columns(self) -> list[str]:
        rows = self.conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position""",
            (self.schema, self.table),
        ).fetchall()
        return [r[0] for r in rows]

    def _ensure_columns(self, columns: list[str]) -> None:
        if self._columns is None:
            raise RuntimeError("prepare() não foi chamado antes de write()")
        missing = [c for c in columns if c not in self._columns]
        for col in missing:
            self.conn.execute(
                sql.SQL("ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {c} text").format(
                    t=self.target, c=sql.Identifier(col)
                )
            )
            self._columns.append(col)
        if missing:
            self.new_columns.extend(missing)
            log.info(
                "schema drift: colunas adicionadas", extra={"table": self.table, "cols": missing}
            )

    def truncate(self) -> None:
        self.conn.execute(sql.SQL("TRUNCATE TABLE {t}").format(t=self.target))

    def write(self, frame: pd.DataFrame, unit_key: str) -> int:
        if frame.empty:
            return 0
        business = list(frame.columns)
        self._ensure_columns(business)

        out = frame.copy()
        out["_dh_batch_id"] = self.run_id
        out["_dh_source_file"] = unit_key
        out["_dh_row_hash"] = row_hash(frame)
        cols = [*business, "_dh_batch_id", "_dh_source_file", "_dh_row_hash"]

        copy_sql = sql.SQL("COPY {d} ({cols}) FROM STDIN").format(
            d=self.target, cols=sql.SQL(", ").join(map(sql.Identifier, cols))
        )
        with self.conn.cursor() as cur, cur.copy(copy_sql) as cp:
            for row in out[cols].to_numpy(dtype=object, na_value=None):
                cp.write_row(row)
        return len(out)
