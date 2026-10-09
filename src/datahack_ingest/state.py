from __future__ import annotations

import socket
import zlib
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

OPS_DDL = """
CREATE TABLE IF NOT EXISTS ops.ingestion_runs (
    run_id          uuid PRIMARY KEY,
    source          text        NOT NULL,
    kind            text        NOT NULL,
    sink            text        NOT NULL,
    load_strategy   text        NOT NULL,
    status          text        NOT NULL CHECK (status IN ('running','success','failed')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    duration_s      numeric GENERATED ALWAYS AS
                    (extract(epoch FROM finished_at - started_at)) STORED,
    units_processed integer     NOT NULL DEFAULT 0,
    units_skipped   integer     NOT NULL DEFAULT 0,
    rows_extracted  bigint      NOT NULL DEFAULT 0,
    rows_loaded     bigint      NOT NULL DEFAULT 0,
    rows_rejected   bigint      NOT NULL DEFAULT 0,
    watermark_from  text,
    watermark_to    text,
    orchestrator_run_id text,
    host            text,
    error           text
);
CREATE INDEX IF NOT EXISTS ingestion_runs_source_started_idx
    ON ops.ingestion_runs (source, started_at DESC);

CREATE TABLE IF NOT EXISTS ops.watermarks (
    source      text PRIMARY KEY,
    value       text        NOT NULL,
    value_type  text        NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    run_id      uuid        NOT NULL
);

CREATE TABLE IF NOT EXISTS ops.file_manifest (
    source      text        NOT NULL,
    file_sha256 text        NOT NULL,
    file_uri    text        NOT NULL,
    file_size   bigint,
    rows_loaded bigint      NOT NULL,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    run_id      uuid        NOT NULL,
    PRIMARY KEY (source, file_sha256)
);

CREATE TABLE IF NOT EXISTS ops.schema_changes (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      text        NOT NULL,
    table_name  text        NOT NULL,
    column_name text        NOT NULL,
    change      text        NOT NULL DEFAULT 'column_added',
    detected_at timestamptz NOT NULL DEFAULT now(),
    run_id      uuid        NOT NULL
);

CREATE TABLE IF NOT EXISTS ops.rejected_rows (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      text        NOT NULL,
    run_id      uuid        NOT NULL,
    reason      text        NOT NULL,
    payload     jsonb       NOT NULL,
    rejected_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rejected_rows_source_idx ON ops.rejected_rows (source, rejected_at);

ALTER TABLE ops.ingestion_runs ADD COLUMN IF NOT EXISTS rows_filtered bigint NOT NULL DEFAULT 0;
ALTER TABLE ops.ingestion_runs ADD COLUMN IF NOT EXISTS rows_deleted bigint NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS ops.data_quality_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      text        NOT NULL,
    run_id      uuid        NOT NULL,
    check_name  text        NOT NULL,
    severity    text        NOT NULL CHECK (severity IN ('warning','error')),
    detail      jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS data_quality_events_source_idx
    ON ops.data_quality_events (source, created_at DESC);

CREATE TABLE IF NOT EXISTS ops.auto_models (
    table_name         text PRIMARY KEY,
    source             text        NOT NULL,
    model_silver       text        NOT NULL,
    model_gold         text        NOT NULL,
    silver_alias       text        NOT NULL,
    gold_alias         text        NOT NULL,
    key_columns        text[]      NOT NULL DEFAULT '{}',
    dedup              text        NOT NULL CHECK (dedup IN ('key','row_hash')),
    materialization    text        NOT NULL CHECK (materialization IN ('table','incremental')),
    row_count          bigint      NOT NULL DEFAULT 0,
    first_generated_at timestamptz NOT NULL DEFAULT now(),
    generated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.data_catalog (
    table_name     text        NOT NULL,
    column_name    text        NOT NULL,
    ordinal        integer     NOT NULL,
    output_name    text        NOT NULL,
    inferred_type  text        NOT NULL,
    type_format    text,
    pii_class      text CHECK (pii_class IN ('identificador','pessoal')),
    hash_digits    boolean     NOT NULL DEFAULT false,
    is_key         boolean     NOT NULL DEFAULT false,
    valid_ratio    numeric,
    null_ratio     numeric,
    distinct_ratio numeric,
    max_length     integer,
    sample_rows    bigint,
    profiled_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, column_name)
);

DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'bronze' AND c.relkind IN ('r', 'p')
          AND pg_has_role(c.relowner, 'USAGE')
          AND NOT EXISTS (
              SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = c.oid AND a.attname = '_dh_deleted_at' AND NOT a.attisdropped
          )
    LOOP
        EXECUTE format('ALTER TABLE bronze.%I ADD COLUMN _dh_deleted_at timestamptz', r.relname);
    END LOOP;
END $$;
"""


def _lock_key(source: str) -> int:
    return zlib.crc32(f"dh_ingest:{source}".encode())


class StateStore:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def ensure(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (_lock_key("__ops_ddl__"),))
            try:
                cur.execute(OPS_DDL)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (_lock_key("__ops_ddl__"),))

    def try_lock(self, source: str) -> bool:
        row = self.conn.execute("SELECT pg_try_advisory_lock(%s)", (_lock_key(source),)).fetchone()
        return bool(row and row[0])

    def unlock(self, source: str) -> None:
        self.conn.execute("SELECT pg_advisory_unlock(%s)", (_lock_key(source),))

    def start_run(self, run_id: str, source: Any, orchestrator_run_id: str | None) -> None:
        self.conn.execute(
            """INSERT INTO ops.ingestion_runs
               (run_id, source, kind, sink, load_strategy, status, orchestrator_run_id, host)
               VALUES (%s, %s, %s, %s, %s, 'running', %s, %s)""",
            (
                run_id,
                source.name,
                source.kind,
                source.sink,
                source.load_strategy,
                orchestrator_run_id,
                socket.gethostname(),
            ),
        )

    def finish_run(self, run_id: str, status: str, metrics: dict, error: str | None = None) -> None:
        self.conn.execute(
            """UPDATE ops.ingestion_runs SET
                 status = %s, finished_at = now(), error = %s,
                 units_processed = %s, units_skipped = %s, rows_extracted = %s,
                 rows_loaded = %s, rows_rejected = %s, watermark_from = %s, watermark_to = %s,
                 rows_filtered = %s, rows_deleted = %s
               WHERE run_id = %s""",
            (
                status,
                (error or "")[:4000] or None,
                metrics.get("units_processed", 0),
                metrics.get("units_skipped", 0),
                metrics.get("rows_extracted", 0),
                metrics.get("rows_loaded", 0),
                metrics.get("rows_rejected", 0),
                metrics.get("watermark_from"),
                metrics.get("watermark_to"),
                metrics.get("rows_filtered", 0),
                metrics.get("rows_deleted", 0),
                run_id,
            ),
        )

    def get_watermark(self, source: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT value, value_type FROM ops.watermarks WHERE source = %s", (source,)
        ).fetchone()
        return (row[0], row[1]) if row else None

    def loaded_file_hashes(self, source: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT file_sha256 FROM ops.file_manifest WHERE source = %s", (source,)
        ).fetchall()
        return {r[0] for r in rows}

    def last_file_hash(self, source: str) -> set[str]:
        row = self.conn.execute(
            """SELECT file_sha256 FROM ops.file_manifest WHERE source = %s
               ORDER BY loaded_at DESC LIMIT 1""",
            (source,),
        ).fetchone()
        return {row[0]} if row else set()

    def recent_volumes(self, source: str, limit: int) -> list[int]:
        rows = self.conn.execute(
            """SELECT rows_extracted FROM ops.ingestion_runs
               WHERE source = %s AND status = 'success' AND units_processed > 0
               ORDER BY started_at DESC LIMIT %s""",
            (source, limit),
        ).fetchall()
        return [int(r[0]) for r in rows]

    def record_event(
        self, source: str, run_id: str, check_name: str, severity: str, detail: dict
    ) -> None:
        self.conn.execute(
            """INSERT INTO ops.data_quality_events (source, run_id, check_name, severity, detail)
               VALUES (%s, %s, %s, %s, %s)""",
            (source, run_id, check_name, severity, Jsonb(detail)),
        )

    def purge(self, retention_days: int) -> dict[str, int]:
        out = {}
        for table, col in (
            ("ingestion_runs", "started_at"),
            ("rejected_rows", "rejected_at"),
            ("schema_changes", "detected_at"),
            ("data_quality_events", "created_at"),
        ):
            cur = self.conn.execute(
                f"DELETE FROM ops.{table} WHERE {col} < now() - make_interval(days => %s)",
                (retention_days,),
            )
            out[table] = cur.rowcount
        return out


def set_watermark(
    conn: psycopg.Connection, source: str, value: str, vtype: str, run_id: str
) -> None:
    conn.execute(
        """INSERT INTO ops.watermarks (source, value, value_type, run_id) VALUES (%s, %s, %s, %s)
           ON CONFLICT (source) DO UPDATE
           SET value = EXCLUDED.value, value_type = EXCLUDED.value_type,
               updated_at = now(), run_id = EXCLUDED.run_id""",
        (source, value, vtype, run_id),
    )


def record_file(conn: psycopg.Connection, source: str, unit: Any, rows: int, run_id: str) -> None:
    conn.execute(
        """INSERT INTO ops.file_manifest
               (source, file_sha256, file_uri, file_size, rows_loaded, run_id)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (source, file_sha256) DO UPDATE
           SET file_uri = EXCLUDED.file_uri, rows_loaded = EXCLUDED.rows_loaded,
               loaded_at = now(), run_id = EXCLUDED.run_id""",
        (source, unit.file_sha256, unit.key, unit.file_size, rows, run_id),
    )


def parse_watermark(value: str, vtype: str) -> Any:
    if vtype == "integer":
        return int(value)
    if vtype == "timestamp":
        return datetime.fromisoformat(value)
    return value
