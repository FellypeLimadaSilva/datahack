from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from pydantic import ValidationError

from datahack_ingest import __version__
from datahack_ingest.catalog import Catalog, load_catalog, required_env_vars
from datahack_ingest.export import Exporter, ExportError, load_export_config
from datahack_ingest.logging_setup import configure
from datahack_ingest.publish import (
    GateReport,
    dbt_gate,
    new_version,
    publish,
    rollback,
    run_dbt,
    source_gate,
)
from datahack_ingest.runner import run_source
from datahack_ingest.settings import Settings
from datahack_ingest.state import StateStore

log = logging.getLogger("datahack_ingest")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dh-ingest",
        description="ELT da Rota do Diploma: Bronze, portão de qualidade, publicação e outputs.",
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--catalog", help="caminho do catálogo (padrão: $DH_CATALOG)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="lista as fontes do catálogo")
    ls.add_argument("--json", action="store_true")

    sub.add_parser("validate", help="valida catálogo e variáveis de ambiente exigidas")
    sub.add_parser("init", help="cria/atualiza as tabelas de controle (schema ops)")

    run = sub.add_parser("run", help="ingere uma ou mais fontes na Bronze")
    run.add_argument("sources", nargs="*", help="nomes das fontes")
    run.add_argument("--all", action="store_true", help="todas as fontes habilitadas")
    run.add_argument("--dry-run", action="store_true", help="extrai e perfila sem gravar")
    run.add_argument("--continue-on-error", action="store_true")

    gt = sub.add_parser("gate", help="verifica se a Bronze tem tudo que a publicação exige")
    gt.add_argument("--orchestrator-run-id", help="considera as ingestões desta execução")

    pb = sub.add_parser("publish", help="promove gold_candidate a gold se os portões passarem")
    pb.add_argument("--run-results", help="run_results.json do dbt (padrão: dbt/target)")
    pb.add_argument("--orchestrator-run-id", help="considera as ingestões desta execução")

    sub.add_parser("rollback", help="volta a versão publicada anterior")

    ex = sub.add_parser("export", help="exporta a Gold publicada para outputs/ (CSV/Parquet)")
    ex.add_argument("--tables", nargs="*", help="tabelas da Gold (padrão: config/exports.yml)")
    ex.add_argument("--config", help="arquivo de exportação (padrão: $DH_EXPORT_CONFIG)")
    ex.add_argument("--out", help="pasta de saída (padrão: $DH_OUTPUTS)")

    pl = sub.add_parser("pipeline", help="ingestão, portões, dbt, publicação e exportação")
    pl.add_argument("--skip-ingest", action="store_true", help="usa a Bronze atual")
    pl.add_argument("--orchestrator-run-id", help="com --skip-ingest: ingestões desta execução")
    pl.add_argument("--dbt-args", nargs=argparse.REMAINDER, default=[])

    mt = sub.add_parser("maintenance", help="ANALYZE na Bronze e expurgo do histórico de controle")
    mt.add_argument("--retention-days", type=int, default=90)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"[erro de configuração] {exc}", file=sys.stderr)
        return 2
    configure(settings.log_format, settings.log_level)
    catalog_path = args.catalog or str(settings.catalog_path)
    try:
        catalog = load_catalog(catalog_path)
    except (ValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[erro de configuração] {catalog_path}: {exc}", file=sys.stderr)
        return 2

    handlers = {
        "list": lambda: _list(catalog, args.json),
        "validate": lambda: _validate(catalog),
        "init": lambda: _init(settings),
        "run": lambda: _run(catalog, settings, args),
        "gate": lambda: _gate(catalog, settings, args.orchestrator_run_id),
        "publish": lambda: _publish(catalog, settings, args.run_results, args.orchestrator_run_id),
        "rollback": lambda: _print(rollback(settings)),
        "export": lambda: _export(settings, args),
        "pipeline": lambda: _pipeline(catalog, settings, args),
        "maintenance": lambda: _maintenance(settings, args.retention_days),
    }
    return handlers[args.cmd]()


def _print(payload: Any, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return code


def _init(settings: Settings) -> int:
    with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
        StateStore(conn).ensure()
    print("schema ops pronto")
    return 0


def _validate(catalog: Catalog) -> int:
    missing = {
        s.name: [v for v in required_env_vars(s) if not os.environ.get(v)]
        for s in catalog.enabled()
    }
    missing = {k: v for k, v in missing.items() if v}
    if missing:
        print(f"[erro] variáveis ausentes: {json.dumps(missing)}", file=sys.stderr)
        return 2
    required = sum(1 for s in catalog.enabled() if s.required)
    print(
        f"catálogo válido: {len(catalog.sources)} fontes "
        f"({len(catalog.enabled())} habilitadas, {required} obrigatórias)"
    )
    return 0


def _ingest(
    catalog: Catalog, settings: Settings, names: list[str] | None, dry_run: bool, keep_going: bool
) -> tuple[list[dict[str, Any]], bool]:
    targets = catalog.enabled() if names is None else [catalog.get(n) for n in names]
    results, failed = [], False
    for source in targets:
        try:
            results.append(run_source(source, settings, dry_run=dry_run).as_dict())
        except Exception as exc:
            failed = True
            results.append(
                {
                    "source": source.name,
                    "required": source.required,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            if not keep_going:
                break
    return results, failed


def _run(catalog: Catalog, settings: Settings, args: argparse.Namespace) -> int:
    if args.all == bool(args.sources):
        print("[erro] informe fontes OU --all", file=sys.stderr)
        return 2
    try:
        results, failed = _ingest(
            catalog,
            settings,
            None if args.all else args.sources,
            args.dry_run,
            args.continue_on_error,
        )
    except KeyError as exc:
        print(f"[erro] {exc}", file=sys.stderr)
        return 2
    return _print(results, 1 if failed else 0)


def _orchestrated_results(
    catalog: Catalog, conn: psycopg.Connection, orchestrator_run_id: str | None
) -> list[dict[str, Any]]:
    if not orchestrator_run_id:
        return []
    rows = conn.execute(
        """SELECT DISTINCT ON (source) source, status, error
           FROM ops.ingestion_runs WHERE orchestrator_run_id = %s
           ORDER BY source, started_at DESC""",
        (orchestrator_run_id,),
    ).fetchall()
    found = {r[0]: {"source": r[0], "status": r[1], "error": r[2]} for r in rows}
    return [
        found.get(s.name, {"source": s.name, "status": "missing", "error": "não executada"})
        for s in catalog.enabled()
    ]


def _gate(catalog: Catalog, settings: Settings, orchestrator_run_id: str | None) -> int:
    with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
        StateStore(conn).ensure()
        results = _orchestrated_results(catalog, conn, orchestrator_run_id)
        report = source_gate(catalog, results, conn)
    return _print(report.as_dict(), 0 if report.ok else 1)


def _publish(
    catalog: Catalog,
    settings: Settings,
    run_results: str | None,
    orchestrator_run_id: str | None,
) -> int:
    path = Path(run_results) if run_results else settings.dbt_target_path
    path = path / "run_results.json" if path.is_dir() else path
    with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
        StateStore(conn).ensure()
        results = _orchestrated_results(catalog, conn, orchestrator_run_id)
        sources = source_gate(catalog, results, conn)
    checks = [sources, dbt_gate(path, 0)]
    outcome = publish(settings, new_version(), checks, sources.detail.get("sources", {}))
    return _print(outcome, 0 if outcome["status"] == "published" else 1)


def _pipeline(catalog: Catalog, settings: Settings, args: argparse.Namespace) -> int:
    version = new_version()
    results: list[dict[str, Any]] = []
    if not args.skip_ingest:
        results, _ = _ingest(catalog, settings, None, dry_run=False, keep_going=True)
    with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
        StateStore(conn).ensure()
        if args.skip_ingest:
            results = _orchestrated_results(catalog, conn, args.orchestrator_run_id)
        sources = source_gate(catalog, results, conn)
    checks: list[GateReport] = [sources]
    summary: dict[str, Any] = {"version": version, "ingest": [_brief(r) for r in results]}
    if sources.ok:
        checks.append(run_dbt(settings, args.dbt_args))
    outcome = publish(settings, version, checks, sources.detail.get("sources", {}))
    summary["checks"] = [c.as_dict() for c in checks if c.stage != "fontes"] + [
        {"stage": "fontes", "ok": sources.ok, "problems": sources.problems}
    ]
    summary["publication"] = outcome
    if outcome["status"] != "published":
        summary["export"] = "não executada: a versão publicada anterior continua valendo"
        return _print(summary, 1)
    release = {
        "version": version,
        "sources": sources.detail.get("sources", {}),
        "dbt": next((c.detail for c in checks if c.stage == "dbt"), {}),
    }
    code, exported = _do_export(settings, None, None, None, release)
    summary["export"] = exported
    return _print(summary, code)


def _brief(result: dict[str, Any]) -> dict[str, Any]:
    keys = ("source", "required", "status", "rows_loaded", "units_processed", "error")
    return {k: result.get(k) for k in keys if result.get(k) is not None}


def _do_export(
    settings: Settings,
    config_path: str | None,
    out: str | None,
    tables: list[str] | None,
    release: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    try:
        config = load_export_config(Path(config_path or settings.export_config_path))
    except (ValidationError, ValueError) as exc:
        return 2, f"configuração inválida: {exc}"
    if not config.tables and not tables:
        return 0, {"status": "skipped", "reason": "nenhuma tabela em exports.yml"}
    exporter = Exporter(
        settings.export_conninfo(),
        Path(out or settings.outputs_dir),
        config,
        release=release or _published_release(settings),
        dbt_manifest=settings.dbt_target_path / "manifest.json",
    )
    try:
        manifest = exporter.run(tables or None)
    except (ExportError, psycopg.Error) as exc:
        return 1, f"falhou: {exc}"
    return 0, {
        "status": "success",
        "version": manifest.get("version"),
        "tables": [
            {"table": t["table"], "rows": t["rows"], "suppressed_rows": t["suppressed_rows"]}
            for t in manifest["tables"]
        ],
    }


def _published_release(settings: Settings) -> dict[str, Any]:
    try:
        with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT version, sources, checks FROM ops.publications "
                "WHERE status = 'published' ORDER BY published_at DESC LIMIT 1"
            ).fetchone()
    except psycopg.Error:
        return {}
    if not row:
        return {}
    dbt = next((c for c in row[2] if c.get("stage") == "dbt"), {})
    return {"version": row[0], "sources": row[1], "dbt": dbt}


def _export(settings: Settings, args: argparse.Namespace) -> int:
    code, payload = _do_export(settings, args.config, args.out, args.tables)
    if code:
        print(f"[erro] exportação: {payload}", file=sys.stderr)
        return code
    return _print(payload)


def _list(catalog: Catalog, as_json: bool) -> int:
    if as_json:
        return _print([s.model_dump(mode="json") for s in catalog.sources])
    for s in catalog.sources:
        flag = "on " if s.enabled else "off"
        need = "obrigatória" if s.required else "opcional"
        print(
            f"[{flag}] {s.name:<26} {need:<11} {s.kind:<4} {s.load_strategy:<6} -> bronze.{s.table}"
        )
    return 0


def _maintenance(settings: Settings, retention_days: int) -> int:
    with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'bronze' AND tableowner = current_user"
        ).fetchall()
        for (t,) in tables:
            conn.execute(sql.SQL("ANALYZE {}").format(sql.Identifier("bronze", t)))
        purged = StateStore(conn).purge(retention_days)
    return _print({"analyzed": len(tables), "purged": purged})


if __name__ == "__main__":
    raise SystemExit(main())
