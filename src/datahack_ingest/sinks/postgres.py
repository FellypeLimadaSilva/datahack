from __future__ import annotations

import hashlib
import logging

import pandas as pd
import psycopg
from psycopg import sql

from datahack_ingest.normalize import row_hash

log = logging.getLogger(__name__)

META_COLUMNS = (
    "_dh_batch_id",
    "_dh_ingested_at",
    "_dh_source_file",
    "_dh_row_hash",
    "_dh_deleted_at",
)
STAGE = "_dh_stage"
KEYS = "_dh_keys"


class DeleteGuardError(RuntimeError):
    pass


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
        strategy: str,
        primary_key: list[str],
        run_id: str,
        schema: str = "bronze",
        delete_detection=None,
    ) -> None:
        self.conn = conn
        self.source_name = source_name
        self.schema = schema
        self.table = table
        self.strategy = strategy
        self.pk = primary_key
        self.run_id = run_id
        self.target = sql.Identifier(schema, table)
        self._columns: list[str] | None = None
        self._unit_columns: set[str] = set()
        self._stage_ready = False
        self._keys_ready = False
        self.delete_detection = delete_detection
        self.rows_deleted = 0
        self.new_columns: list[str] = []

    def prepare(self) -> None:
        self.conn.execute(
            sql.SQL(
                """CREATE TABLE IF NOT EXISTS {t} (
                     _dh_batch_id    uuid        NOT NULL,
                     _dh_ingested_at timestamptz NOT NULL DEFAULT now(),
                     _dh_source_file text,
                     _dh_row_hash    text,
                     _dh_deleted_at  timestamptz
                   )"""
            ).format(t=self.target)
        )
        self.conn.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {i} ON {t} USING brin (_dh_ingested_at)").format(
                i=sql.Identifier(_index_name(self.table, "ingested_brin")), t=self.target
            )
        )
        self._columns = self._existing_columns()
        if "_dh_deleted_at" not in self._columns:
            self.conn.execute(
                sql.SQL(
                    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS _dh_deleted_at timestamptz"
                ).format(t=self.target)
            )
            self._columns.append("_dh_deleted_at")

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
            if self._stage_ready:
                self.conn.execute(
                    sql.SQL("ALTER TABLE {s} ADD COLUMN IF NOT EXISTS {c} text").format(
                        s=sql.Identifier(STAGE), c=sql.Identifier(col)
                    )
                )
            self._columns.append(col)
        if missing:
            self.new_columns.extend(missing)
            log.info(
                "schema drift: colunas adicionadas", extra={"table": self.table, "cols": missing}
            )
        if self.strategy == "merge":
            self._ensure_pk_index()

    def _ensure_pk_index(self) -> None:
        absent = [c for c in self.pk if c not in (self._columns or [])]
        if absent:
            raise ValueError(f"{self.source_name}: primary_key ausente nos dados: {absent}")
        self.conn.execute(
            sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {i} ON {t} ({cols})").format(
                i=sql.Identifier(_index_name(self.table, "pk_uidx")),
                t=self.target,
                cols=sql.SQL(", ").join(map(sql.Identifier, self.pk)),
            )
        )

    def truncate(self) -> None:
        self.conn.execute(sql.SQL("TRUNCATE TABLE {t}").format(t=self.target))

    def begin_unit(self) -> None:
        self._unit_columns = set()
        if self.strategy == "merge":
            self.conn.execute(
                sql.SQL(
                    "CREATE TEMP TABLE {s} (LIKE {t} INCLUDING DEFAULTS) ON COMMIT DROP"
                ).format(s=sql.Identifier(STAGE), t=self.target)
            )
            self.conn.execute(
                sql.SQL(
                    "ALTER TABLE {s} ADD COLUMN _dh_seq bigint GENERATED ALWAYS AS IDENTITY"
                ).format(s=sql.Identifier(STAGE))
            )
            self._stage_ready = True

    def write(self, frame: pd.DataFrame, unit_key: str) -> int:
        if frame.empty:
            return 0
        business = list(frame.columns)
        self._ensure_columns(business)
        self._unit_columns.update(business)

        out = frame.copy()
        out["_dh_batch_id"] = self.run_id
        out["_dh_source_file"] = unit_key
        out["_dh_row_hash"] = row_hash(frame)
        cols = [*business, "_dh_batch_id", "_dh_source_file", "_dh_row_hash"]
        dest = sql.Identifier(STAGE) if self.strategy == "merge" else self.target

        copy_sql = sql.SQL("COPY {d} ({cols}) FROM STDIN").format(
            d=dest, cols=sql.SQL(", ").join(map(sql.Identifier, cols))
        )
        with self.conn.cursor() as cur, cur.copy(copy_sql) as cp:
            for row in out[cols].to_numpy(dtype=object, na_value=None):
                cp.write_row(row)
        return len(out)

    def end_unit(self) -> tuple[int, int]:
        if self.strategy != "merge":
            return -1, 0
        if not self._unit_columns:
            if self.delete_detection and self._keys_ready:
                self.rows_deleted += self._apply_deletes(KEYS)
            self._drop_stage()
            return 0, 0

        stage = sql.Identifier(STAGE)
        pk = [sql.Identifier(c) for c in self.pk]
        pk_null = sql.SQL(" OR ").join(sql.SQL("{} IS NULL").format(c) for c in pk)
        pk_ok = sql.SQL(" AND ").join(sql.SQL("{} IS NOT NULL").format(c) for c in pk)

        rejected = self.conn.execute(
            sql.SQL(
                """INSERT INTO ops.rejected_rows (source, run_id, reason, payload)
                   SELECT %s, %s, 'null_primary_key', to_jsonb(s) - '_dh_seq'
                   FROM {s} s WHERE {cond}"""
            ).format(s=stage, cond=pk_null),
            (self.source_name, self.run_id),
        ).rowcount

        write_cols = [c for c in self._columns if c in self._unit_columns or c in META_COLUMNS]
        updatable = [c for c in write_cols if c not in self.pk]
        ident = [sql.Identifier(c) for c in write_cols]
        upsert = sql.SQL(
            """INSERT INTO {t} AS tgt ({cols})
               SELECT {cols} FROM (
                   SELECT DISTINCT ON ({pk}) * FROM {s} WHERE {pk_ok} ORDER BY {pk}, _dh_seq DESC
               ) d
               ON CONFLICT ({pk}) DO UPDATE SET {sets}
               WHERE tgt._dh_row_hash IS DISTINCT FROM EXCLUDED._dh_row_hash
                  OR tgt._dh_deleted_at IS NOT NULL"""
        ).format(
            t=self.target,
            cols=sql.SQL(", ").join(ident),
            pk=sql.SQL(", ").join(pk),
            s=stage,
            pk_ok=pk_ok,
            sets=sql.SQL(", ").join(
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in updatable
            ),
        )
        written = self.conn.execute(upsert).rowcount
        if self.delete_detection:
            self.rows_deleted += self._apply_deletes(KEYS if self._keys_ready else STAGE)
        self._drop_stage()
        return written, rejected

    def _drop_stage(self) -> None:
        for name, flag in ((STAGE, "_stage_ready"), (KEYS, "_keys_ready")):
            if getattr(self, flag):
                self.conn.execute(
                    sql.SQL("DROP TABLE IF EXISTS {s}").format(s=sql.Identifier(name))
                )
                setattr(self, flag, False)

    def load_keys(self, frames) -> int:
        cols = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in self.pk)
        self.conn.execute(
            sql.SQL("CREATE TEMP TABLE {k} ({cols}) ON COMMIT DROP").format(
                k=sql.Identifier(KEYS), cols=cols
            )
        )
        self._keys_ready = True
        copy_sql = sql.SQL("COPY {k} ({cols}) FROM STDIN").format(
            k=sql.Identifier(KEYS), cols=sql.SQL(", ").join(map(sql.Identifier, self.pk))
        )
        total = 0
        for frame in frames:
            missing = [c for c in self.pk if c not in frame.columns]
            if missing:
                raise ValueError(f"{self.source_name}: keys_query sem colunas da chave {missing}")
            with self.conn.cursor() as cur, cur.copy(copy_sql) as cp:
                for row in frame[self.pk].to_numpy(dtype=object, na_value=None):
                    cp.write_row(row)
            total += len(frame)
        return total

    def _apply_deletes(self, keys_relation: str) -> int:
        dd = self.delete_detection
        keys = sql.Identifier(keys_relation)
        pk_ok = sql.SQL(" AND ").join(
            sql.SQL("{} IS NOT NULL").format(sql.Identifier(c)) for c in self.pk
        )
        match = sql.SQL(" AND ").join(
            sql.SQL("k.{c} = t.{c}").format(c=sql.Identifier(c)) for c in self.pk
        )
        missing = sql.SQL(
            "t._dh_deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM {k} k WHERE {m})"
        ).format(k=keys, m=match)

        n_keys = self.conn.execute(
            sql.SQL("SELECT count(*) FROM {k} WHERE {ok}").format(k=keys, ok=pk_ok)
        ).fetchone()[0]
        if n_keys == 0:
            raise DeleteGuardError(
                f"{self.source_name}: snapshot sem chaves; exclusão em massa bloqueada"
            )
        active = self.conn.execute(
            sql.SQL("SELECT count(*) FROM {t} WHERE _dh_deleted_at IS NULL").format(t=self.target)
        ).fetchone()[0]
        candidates = self.conn.execute(
            sql.SQL("SELECT count(*) FROM {t} t WHERE {m}").format(t=self.target, m=missing)
        ).fetchone()[0]
        if active and candidates / active > dd.max_delete_ratio:
            raise DeleteGuardError(
                f"{self.source_name}: {candidates} de {active} registros sumiram da origem "
                f"(> {dd.max_delete_ratio:.0%}); exclusão bloqueada por segurança"
            )
        if not candidates:
            return 0
        if dd.mode == "hard":
            stmt = sql.SQL("DELETE FROM {t} t WHERE {m}").format(t=self.target, m=missing)
            return self.conn.execute(stmt).rowcount
        stmt = sql.SQL(
            "UPDATE {t} t SET _dh_deleted_at = now(), _dh_ingested_at = now(), _dh_batch_id = %s "
            "WHERE {m}"
        ).format(t=self.target, m=missing)
        return self.conn.execute(stmt, (self.run_id,)).rowcount
