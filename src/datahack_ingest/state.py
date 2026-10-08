from __future__ import annotations

import socket
import zlib
from datetime import datetime
from typing import Any

import psycopg

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
                 rows_loaded = %s, rows_rejected = %s, watermark_from = %s, watermark_to = %s
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

    def purge(self, retention_days: int) -> dict[str, int]:
        out = {}
        for table, col in (
            ("ingestion_runs", "started_at"),
            ("rejected_rows", "rejected_at"),
            ("schema_changes", "detected_at"),
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
