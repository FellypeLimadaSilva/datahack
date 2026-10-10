from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from pydantic import ValidationError

from datahack_ingest import __version__
from datahack_ingest.alerting import Alert, configured_channels, send_alert
from datahack_ingest.catalog import required_env_vars
from datahack_ingest.discovery import ResolvedCatalog, resolve_catalog
from datahack_ingest.export import Exporter, ExportError, load_export_config
from datahack_ingest.logging_setup import configure
from datahack_ingest.modelgen import ModelGenerator
from datahack_ingest.runner import run_source
from datahack_ingest.settings import Settings
from datahack_ingest.state import StateStore

log = logging.getLogger("datahack_ingest")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dh-ingest", description="Ingestão Bronze e geração automática de Silver/Gold."
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--catalog", help="caminho do catálogo (padrão: $DH_CATALOG)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="lista as fontes do catálogo")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--enabled-only", action="store_true")

    dc = sub.add_parser(
        "discover", help="mostra o que a inbox gerou de fontes e o que foi ignorado"
    )
    dc.add_argument("--json", action="store_true")

    sub.add_parser("validate", help="valida catálogo e variáveis de ambiente exigidas")
    sub.add_parser("init", help="cria/atualiza as tabelas de controle (schema ops)")

    run = sub.add_parser("run", help="executa a ingestão de uma ou mais fontes")
    run.add_argument("sources", nargs="*", help="nomes das fontes")
    run.add_argument("--all", action="store_true", help="todas as fontes habilitadas")
    run.add_argument("--dry-run", action="store_true", help="extrai e perfila sem gravar")
    run.add_argument("--continue-on-error", action="store_true")

    gm = sub.add_parser("generate-models", help="gera Silver e Gold no dbt a partir da Bronze")
    gm.add_argument("--reset", action="store_true", help="refaz a inferência de tipos e chaves")
    gm.add_argument("--dry-run", action="store_true", help="perfila sem gravar arquivos nem ops")

    ex = sub.add_parser("export", help="exporta tabelas da Gold para outputs/ (CSV/Parquet)")
    ex.add_argument("--tables", nargs="*", help="tabelas da Gold (padrão: config/exports.yml)")
    ex.add_argument("--config", help="arquivo de exportação (padrão: $DH_EXPORT_CONFIG)")
    ex.add_argument("--out", help="pasta de saída (padrão: $DH_OUTPUTS)")

    sub.add_parser("alert-test", help="envia um alerta de teste para os canais configurados")

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
        resolved = resolve_catalog(settings, catalog_path)
    except (ValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[erro de configuração] {catalog_path}: {exc}", file=sys.stderr)
        return 2
    if args.cmd == "list":
        return _list(resolved, args.json, args.enabled_only)

    if args.cmd == "discover":
        return _discover(resolved, args.json)

    if args.cmd == "validate":
        return _validate(resolved)

    if args.cmd == "generate-models":
        return _generate(settings, resolved, args.reset, args.dry_run)

    if args.cmd == "export":
        return _export(settings, args)

    if args.cmd == "init":
        with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
            StateStore(conn).ensure()
        print("schema ops pronto")
        return 0

    if args.cmd == "alert-test":
        channels = configured_channels()
        if not channels:
            print("[erro] nenhum canal configurado (DH_ALERT_*)", file=sys.stderr)
            return 2
        delivered = send_alert(
            Alert(
                title="Teste de alerta",
                message="Canal de alertas da plataforma DataHack ativo.",
                severity="error",
                context={"origem": "dh-ingest alert-test"},
            )
        )
        print(json.dumps({"configured": channels, "delivered": delivered}))
        return 0 if set(delivered) == set(channels) else 1

    if args.cmd == "maintenance":
        return _maintenance(settings, args.retention_days)

    return _run(resolved, settings, args)


def _validate(resolved: ResolvedCatalog) -> int:
    catalog = resolved.catalog
    missing = {
        s.name: [v for v in required_env_vars(s) if not os.environ.get(v)]
        for s in catalog.enabled()
    }
    missing = {k: v for k, v in missing.items() if v}
    if missing:
        print(f"[erro] variáveis ausentes: {json.dumps(missing)}", file=sys.stderr)
        return 2
    if resolved.errors:
        print(f"[erro] inbox: {json.dumps(resolved.errors, ensure_ascii=False)}", file=sys.stderr)
        return 2
    print(f"catálogo válido: {len(catalog.sources)} fontes ({len(catalog.enabled())} habilitadas)")
    return 0


def _run(resolved: ResolvedCatalog, settings: Settings, args: argparse.Namespace) -> int:
    catalog = resolved.catalog
    if args.all == bool(args.sources):
        print("[erro] informe fontes OU --all", file=sys.stderr)
        return 2
    try:
        targets = catalog.enabled() if args.all else [catalog.get(n) for n in args.sources]
    except KeyError as exc:
        print(f"[erro] {exc}", file=sys.stderr)
        return 2

    results, failed = [], False
    if args.all and resolved.errors:
        failed = True
        results += [
            {"source": e["path"], "status": "failed", "error": e["reason"]} for e in resolved.errors
        ]
        if not args.continue_on_error:
            targets = []
    for source in targets:
        try:
            results.append(run_source(source, settings, dry_run=args.dry_run).as_dict())
        except Exception as exc:
            failed = True
            results.append({"source": source.name, "status": "failed", "error": str(exc)})
            if not args.continue_on_error:
                break
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 1 if failed else 0


def _list(resolved: ResolvedCatalog, as_json: bool, enabled_only: bool) -> int:
    catalog = resolved.catalog
    items = catalog.enabled() if enabled_only else catalog.sources
    if as_json:
        payload = [{**s.model_dump(mode="json"), "origin": resolved.origin(s.name)} for s in items]
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    for s in items:
        flag = "on " if s.enabled else "off"
        print(
            f"[{flag}] {s.name:<32} {resolved.origin(s.name):<8} {s.kind:<4} "
            f"{s.load_strategy:<6} -> {s.sink}:{s.table}"
        )
    return 0


def _source_location(source) -> str:
    opts = getattr(source, "file", None)
    if opts is None:
        return source.description.removeprefix("Descoberta automática: ")
    if opts.include != ["*"] and not opts.recursive:
        return ", ".join(f"{opts.path}/{name}" for name in opts.include)
    return opts.path


def _discover(resolved: ResolvedCatalog, as_json: bool) -> int:
    found = [s for s in resolved.catalog.sources if resolved.origin(s.name) == "inbox"]
    payload = {
        "sources": [
            {
                "name": s.name,
                "kind": s.kind,
                "format": getattr(getattr(s, "file", None), "format", "sqlite"),
                "path": _source_location(s),
                "table": f"bronze.{s.table}",
            }
            for s in found
        ],
        "ignored": resolved.ignored,
        "errors": resolved.errors,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in payload["sources"]:
            print(f"[fonte]   {item['name']:<32} {item['format']:<8} {item['path']}")
        for item in resolved.ignored:
            print(f"[ignorado] {item['path']}: {item['reason']}")
        for item in resolved.errors:
            print(f"[erro]    {item['path']}: {item['reason']}")
    return 2 if resolved.errors else 0


def _generate(settings: Settings, resolved: ResolvedCatalog, reset: bool, dry_run: bool) -> int:
    if not settings.auto_models_enabled:
        print(json.dumps({"status": "disabled", "reason": "DH_AUTO_MODELS=false"}))
        return 0
    with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
        StateStore(conn).ensure()
        generator = ModelGenerator(settings, resolved.catalog, reset=reset)
        specs = generator.run(conn, write=not dry_run)
    summary = {
        "status": "dry_run" if dry_run else "success",
        "models_dir": str(settings.dbt_project_dir / "models" / "auto"),
        "tables": [
            {
                "table": s.table,
                "silver": f"silver.{s.silver_alias}",
                "gold": f"gold.{s.gold_alias}",
                "rows": s.row_count,
                "dedup": s.dedup,
                "key": s.key_columns,
                "materialization": s.materialization,
                "types": {c.output_name: c.inferred_type for c in s.columns},
                "pii": [c.output_name for c in s.columns if c.pii_class == "identificador"],
                "personal": [c.output_name for c in s.columns if c.pii_class == "pessoal"],
            }
            for s in specs
        ],
        "skipped": generator.skipped,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _export(settings: Settings, args: argparse.Namespace) -> int:
    try:
        config = load_export_config(Path(args.config or settings.export_config_path))
    except (ValidationError, ValueError) as exc:
        print(f"[erro de configuração] exportação: {exc}", file=sys.stderr)
        return 2
    if not config.tables and not args.tables:
        print(json.dumps({"status": "skipped", "reason": "nenhuma tabela em exports.yml"}))
        return 0
    exporter = Exporter(settings.export_conninfo(), Path(args.out or settings.outputs_dir), config)
    try:
        manifest = exporter.run(args.tables or None)
    except (ExportError, psycopg.Error) as exc:
        print(f"[erro] exportação: {exc}", file=sys.stderr)
        return 1
    summary = [
        {
            "table": t["table"],
            "rows": t["rows"],
            "suppressed_rows": t["suppressed_rows"],
            "base_columns": t["base_columns"],
            "files": [f["file"] for f in t["files"]],
        }
        for t in manifest["tables"]
    ]
    print(json.dumps({"status": "success", "tables": summary}, ensure_ascii=False, indent=2))
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
    print(json.dumps({"analyzed": len(tables), "purged": purged}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
