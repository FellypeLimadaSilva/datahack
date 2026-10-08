from __future__ import annotations

import argparse
import json
import logging
import os
import sys

import psycopg
from psycopg import sql
from pydantic import ValidationError

from datahack_ingest import __version__
from datahack_ingest.catalog import load_catalog, required_env_vars
from datahack_ingest.logging_setup import configure
from datahack_ingest.runner import run_source
from datahack_ingest.settings import Settings
from datahack_ingest.state import StateStore

log = logging.getLogger("datahack_ingest")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dh-ingest", description="Ingestão ELT para a camada Bronze.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--catalog", help="caminho do catálogo (padrão: $DH_CATALOG)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="lista as fontes do catálogo")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--enabled-only", action="store_true")

    sub.add_parser("validate", help="valida catálogo e variáveis de ambiente exigidas")
    sub.add_parser("init", help="cria/atualiza as tabelas de controle (schema ops)")

    run = sub.add_parser("run", help="executa a ingestão de uma ou mais fontes")
    run.add_argument("sources", nargs="*", help="nomes das fontes")
    run.add_argument("--all", action="store_true", help="todas as fontes habilitadas")
    run.add_argument("--dry-run", action="store_true", help="extrai e perfila sem gravar")
    run.add_argument("--continue-on-error", action="store_true")

    mt = sub.add_parser("maintenance", help="ANALYZE na Bronze e expurgo do histórico de controle")
    mt.add_argument("--retention-days", type=int, default=90)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.from_env()
    configure(settings.log_format, settings.log_level)
    catalog_path = args.catalog or str(settings.catalog_path)

    try:
        catalog = load_catalog(catalog_path)
    except (ValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[erro de configuração] {catalog_path}: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "list":
        items = catalog.enabled() if args.enabled_only else catalog.sources
        if args.json:
            print(json.dumps([s.model_dump(mode="json") for s in items], ensure_ascii=False))
        else:
            for s in items:
                flag = "on " if s.enabled else "off"
                print(
                    f"[{flag}] {s.name:<28} {s.kind:<5} {s.load_strategy:<7} -> {s.sink}:{s.table}"
                )
        return 0

    if args.cmd == "validate":
        missing = {
            s.name: [v for v in required_env_vars(s) if not os.environ.get(v)]
            for s in catalog.enabled()
        }
        missing = {k: v for k, v in missing.items() if v}
        if missing:
            print(f"[erro] variáveis ausentes: {json.dumps(missing)}", file=sys.stderr)
            return 2
        print(
            f"catálogo válido: {len(catalog.sources)} fontes ({len(catalog.enabled())} habilitadas)"
        )
        return 0

    if args.cmd == "init":
        with psycopg.connect(settings.conninfo(), autocommit=True) as conn:
            StateStore(conn).ensure()
        print("schema ops pronto")
        return 0

    if args.cmd == "maintenance":
        return _maintenance(settings, args.retention_days)

    if args.all == bool(args.sources):
        print("[erro] informe fontes OU --all", file=sys.stderr)
        return 2
    try:
        targets = catalog.enabled() if args.all else [catalog.get(n) for n in args.sources]
    except KeyError as exc:
        print(f"[erro] {exc}", file=sys.stderr)
        return 2

    results, failed = [], False
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
