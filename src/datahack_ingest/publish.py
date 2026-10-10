from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from datahack_ingest.catalog import Catalog
from datahack_ingest.settings import Settings

log = logging.getLogger(__name__)

BLOCKING_STATUSES = {"error", "fail", "runtime error", "skipped"}


class GateError(RuntimeError):
    def __init__(self, stage: str, problems: list[str]) -> None:
        super().__init__(f"{stage}: " + "; ".join(problems))
        self.stage = stage
        self.problems = problems


@dataclass
class GateReport:
    stage: str
    ok: bool
    problems: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "ok": self.ok, "problems": self.problems, **self.detail}


def new_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def source_gate(
    catalog: Catalog, results: list[dict[str, Any]], conn: psycopg.Connection
) -> GateReport:
    problems: list[str] = []
    by_name = {r["source"]: r for r in results}
    loaded: dict[str, Any] = {}
    for source in catalog.enabled():
        run = by_name.get(source.name)
        if source.required and run is not None and run.get("status") != "success":
            problems.append(f"{source.name}: ingestão falhou ({run.get('error')})")
        exists = conn.execute(
            "SELECT to_regclass(%s) IS NOT NULL", (f"bronze.{source.table}",)
        ).fetchone()[0]
        if not exists:
            if source.required:
                problems.append(f"{source.name}: bronze.{source.table} não existe")
            loaded[source.name] = {"rows": 0, "files": []}
            continue
        rows = conn.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("bronze", source.table))
        ).fetchone()[0]
        if source.required and rows == 0:
            problems.append(f"{source.name}: bronze.{source.table} vazia")
        columns = {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'bronze' AND table_name = %s",
                (source.table,),
            ).fetchall()
        }
        missing = [c for c in source.essential_columns if c not in columns]
        if missing and rows:
            problems.append(f"{source.name}: colunas essenciais ausentes {missing}")
        files = conn.execute(
            "SELECT file_uri, file_sha256, rows_loaded FROM ops.file_manifest "
            "WHERE source = %s ORDER BY file_uri",
            (source.name,),
        ).fetchall()
        loaded[source.name] = {
            "rows": rows,
            "required": source.required,
            "files": [{"file": Path(uri).name, "sha256": sha, "rows": n} for uri, sha, n in files],
        }
    return GateReport("fontes", not problems, problems, {"sources": loaded})


def run_dbt(settings: Settings, extra: list[str] | None = None) -> GateReport:
    target_path = settings.dbt_target_path
    env = {
        **os.environ,
        "DH_GOLD_SCHEMA": settings.candidate_schema,
        "DBT_TARGET": settings.dbt_target,
    }
    env.setdefault("DBT_PROFILES_DIR", str(settings.dbt_project_dir))
    dbt = (
        os.environ.get("DBT_BIN")
        or shutil.which("dbt")
        or str(Path(sys.executable).with_name("dbt"))
    )
    cmd = [dbt, "build", "--project-dir", str(settings.dbt_project_dir), *(extra or [])]
    log.info("dbt build no schema candidato", extra={"cmd": cmd})
    (target_path / "run_results.json").unlink(missing_ok=True)
    proc = subprocess.run(cmd, env=env, check=False)
    return dbt_gate(target_path / "run_results.json", proc.returncode)


def dbt_gate(run_results: Path, returncode: int) -> GateReport:
    if not run_results.exists():
        return GateReport("dbt", False, [f"dbt saiu com código {returncode} sem run_results"])
    payload = json.loads(run_results.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    problems: list[str] = []
    warnings: list[str] = []
    for r in payload.get("results", []):
        status = str(r.get("status"))
        counts[status] = counts.get(status, 0) + 1
        node = r.get("unique_id", "?")
        if status in BLOCKING_STATUSES:
            problems.append(f"{node}: {status}")
        elif status == "warn":
            warnings.append(node)
    if returncode != 0 and not problems:
        problems.append(f"dbt saiu com código {returncode}")
    detail = {
        "invocation_id": payload.get("metadata", {}).get("invocation_id"),
        "counts": counts,
        "warnings": warnings,
    }
    return GateReport("dbt", not problems, problems, detail)


def publish(
    settings: Settings, version: str, checks: list[GateReport], sources: dict[str, Any]
) -> dict[str, Any]:
    failed = [c for c in checks if not c.ok]
    gold = sql.Identifier(settings.gold_schema)
    candidate = sql.Identifier(settings.candidate_schema)
    previous = sql.Identifier(settings.previous_schema)
    bi = sql.Identifier(settings.bi_role)
    with psycopg.connect(settings.transform_conninfo()) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('dh_publish'))")
        current = _current_version(conn, settings.gold_schema)
        if failed:
            reason = "; ".join(p for c in failed for p in c.problems)[:4000]
            _record(conn, version, "rejected", current, reason, sources, checks)
            return {"status": "rejected", "version": version, "kept": current, "reason": reason}
        relations = conn.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind IN ('r', 'v', 'm')",
            (settings.candidate_schema,),
        ).fetchone()[0]
        if relations == 0:
            reason = f"{settings.candidate_schema} vazio"
            _record(conn, version, "rejected", current, reason, sources, checks)
            return {"status": "rejected", "version": version, "kept": current, "reason": reason}
        conn.execute("SET LOCAL lock_timeout = '15s'")
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(previous))
        if _schema_exists(conn, settings.gold_schema):
            conn.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(gold, previous))
            conn.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(previous, bi))
        conn.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(candidate, gold))
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(candidate))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(gold, bi))
        conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(gold, bi))
        conn.execute(
            sql.SQL("COMMENT ON SCHEMA {} IS {}").format(
                gold, sql.Literal(f"Camada consumida pelo BI. Versão publicada: {version}")
            )
        )
        _record(conn, version, "published", current, None, sources, checks)
    log.info("versão publicada", extra={"version": version, "previous": current})
    return {"status": "published", "version": version, "previous": current}


def rollback(settings: Settings) -> dict[str, Any]:
    gold = sql.Identifier(settings.gold_schema)
    previous = sql.Identifier(settings.previous_schema)
    swap = sql.Identifier(f"{settings.gold_schema}_swap")
    bi = sql.Identifier(settings.bi_role)
    with psycopg.connect(settings.transform_conninfo()) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('dh_publish'))")
        if not _schema_exists(conn, settings.previous_schema):
            return {"status": "noop", "reason": f"{settings.previous_schema} não existe"}
        before = _current_version(conn, settings.gold_schema)
        after = _current_version(conn, settings.previous_schema)
        conn.execute("SET LOCAL lock_timeout = '15s'")
        conn.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(gold, swap))
        conn.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(previous, gold))
        conn.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(swap, previous))
        conn.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(previous, bi))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(gold, bi))
        conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(gold, bi))
    return {"status": "rolled_back", "from": before, "to": after}


def _schema_exists(conn: psycopg.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (name,)).fetchone()
    return row is not None


def _current_version(conn: psycopg.Connection, schema: str) -> str | None:
    row = conn.execute(
        "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname = %s",
        (schema,),
    ).fetchone()
    if not row or not row[0] or "Versão publicada: " not in row[0]:
        return None
    return row[0].rsplit("Versão publicada: ", 1)[1].strip()


def _record(
    conn: psycopg.Connection,
    version: str,
    status: str,
    previous: str | None,
    reason: str | None,
    sources: dict[str, Any],
    checks: list[GateReport],
) -> None:
    conn.execute(
        """INSERT INTO ops.publications (version, status, previous, reason, sources, checks)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (version, status, previous, reason, Jsonb(sources), Jsonb([c.as_dict() for c in checks])),
    )
