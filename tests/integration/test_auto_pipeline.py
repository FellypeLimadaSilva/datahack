from __future__ import annotations

import dataclasses
import importlib.util
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from datahack_ingest.discovery import resolve_catalog
from datahack_ingest.export import ExportConfig, Exporter
from datahack_ingest.modelgen import ModelGenerator
from datahack_ingest.runner import run_source
from datahack_ingest.state import StateStore

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
DBT = shutil.which("dbt") or str(Path(sys.executable).with_name("dbt"))


def _messy_module():
    spec = importlib.util.spec_from_file_location(
        "generate_messy_data", ROOT / "scripts" / "generate_messy_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dbt_conninfo(settings) -> str | None:
    password = os.environ.get("WAREHOUSE_DBT_PASSWORD")
    if not password:
        return None
    return psycopg.conninfo.make_conninfo(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_db,
        user=os.environ.get("WAREHOUSE_DBT_USER", "dh_transformer"),
        password=password,
    )


@pytest.fixture
def auto_env(settings, tmp_path):
    if not Path(DBT).exists():
        pytest.skip("dbt não instalado")
    if not _dbt_conninfo(settings):
        pytest.skip("WAREHOUSE_DBT_PASSWORD ausente")
    prefix = "t" + "".join(chr(97 + b % 26) for b in uuid.uuid4().bytes[:6]) + "_"
    inbox = tmp_path / "landing" / "inbox"
    _messy_module().main(["--out", str(inbox), "--rows", "3000"])
    for entry in list(inbox.iterdir()):
        if not entry.name.startswith((".", "~$")):
            entry.rename(entry.with_name(prefix + entry.name))
    zipped = inbox / f"{prefix}export_erp"
    zipped.mkdir()
    (inbox / f"{prefix}export_erp.zip").rename(zipped / "export_erp.zip")
    for archive in inbox.glob(f"{prefix}microdados_censo_*.zip"):
        _prefix_members(archive, prefix)
    project = tmp_path / "dbt"
    shutil.copytree(
        ROOT / "dbt",
        project,
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages", "auto"),
    )
    catalog = tmp_path / "sources.yml"
    catalog.write_text("version: 1\nsources: []\n", encoding="utf-8")
    s = dataclasses.replace(
        settings,
        catalog_path=catalog,
        landing_uri=str(tmp_path / "landing"),
        examples_enabled=False,
        inbox_settle_seconds=0,
        dbt_project_dir=project,
        auto_incremental_rows=1000,
    )
    yield s, inbox, prefix, project
    _cleanup(s, prefix)


def _prefix_members(archive: Path, prefix: str) -> None:
    with zipfile.ZipFile(archive) as src:
        members = [(i.filename, src.read(i)) for i in src.infolist() if not i.is_dir()]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as dst:
        for name, data in members:
            head, _, tail = name.rpartition("/")
            dst.writestr(f"{head}/{prefix}{tail}" if head else prefix + tail, data)


def _cleanup(s, prefix: str) -> None:
    like = prefix.replace("_", r"\_") + "%"
    with psycopg.connect(_dbt_conninfo(s), autocommit=True) as c:
        for schema in ("gold", "silver"):
            rows = c.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name LIKE %s",
                (schema, like),
            ).fetchall()
            for name, kind in rows:
                stmt = (
                    "DROP VIEW IF EXISTS {} CASCADE"
                    if kind == "VIEW"
                    else "DROP TABLE IF EXISTS {} CASCADE"
                )
                c.execute(sql.SQL(stmt).format(sql.Identifier(schema, name)))
    with psycopg.connect(s.conninfo(), autocommit=True) as c:
        for (name,) in c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'bronze' AND table_name LIKE %s",
            (like,),
        ).fetchall():
            c.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier("bronze", name)))
        for table, column in (
            ("auto_models", "table_name"),
            ("data_catalog", "table_name"),
            ("ingestion_runs", "source"),
            ("file_manifest", "source"),
            ("schema_changes", "source"),
            ("rejected_rows", "source"),
        ):
            c.execute(
                sql.SQL("DELETE FROM {} WHERE {} LIKE %s").format(
                    sql.Identifier("ops", table), sql.Identifier(column)
                ),
                (like,),
            )


def _cycle(s, prefix: str, extra: tuple[str, ...] = ()):
    resolved = resolve_catalog(s)
    results = [run_source(src, s) for src in resolved.catalog.enabled()]
    assert all(r.status == "success" for r in results)
    with psycopg.connect(s.conninfo(), autocommit=True) as conn:
        StateStore(conn).ensure()
        specs = ModelGenerator(s, resolved.catalog, prune=False).run(conn)
    env = {
        **os.environ,
        "DH_EXAMPLES": "false",
        "DBT_PROFILES_DIR": str(ROOT / "dbt"),
        "DBT_TARGET": os.environ.get("DBT_TARGET", "dev"),
    }
    proc = subprocess.run(
        [
            DBT,
            "build",
            "--select",
            "tag:auto",
            *extra,
            "--target-path",
            str(s.dbt_project_dir / "target"),
        ],
        cwd=s.dbt_project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-4000:]
    return resolved, {spec.table.removeprefix(prefix): spec for spec in specs}, proc.stdout


def _query(s, query: str, *params):
    with psycopg.connect(_dbt_conninfo(s)) as c:
        return c.execute(query, params).fetchall()


def test_any_file_reaches_gold_automatically(auto_env):
    s, inbox, prefix, _ = auto_env
    resolved, specs, out = _cycle(s, prefix)

    assert {i["path"].rsplit("/", 1)[-1] for i in resolved.ignored} >= {f"{prefix}LEIA-ME.pdf"}
    assert set(specs) == {
        "clientes",
        "pedidos",
        "estoque_produtos",
        "estoque_movimentos",
        "notas_fiscais",
        "eventos",
        "export_erp",
        "catalogo",
        "legado_fornecedores",
        "legado_contas_a_pagar",
        "reservadas",
        "transacoes",
        "trajetoria",
        "microdados_cadastro_cursos",
        "microdados_ed_sup_ies",
    }
    types = {k: {c.output_name: c.inferred_type for c in v.columns} for k, v in specs.items()}
    assert types["clientes"]["data_nascimento"] == "date"
    assert types["clientes"]["renda_mensal"] == "numeric"
    assert types["clientes"]["codigo"] == "text"
    assert {"cpf_hash", "e_mail_hash", "telefone_hash"} <= set(types["clientes"])
    assert types["pedidos"]["criado_em"] == "timestamptz"
    assert types["pedidos"]["itens"] == "jsonb"
    assert types["estoque_movimentos"]["data"] == "date"
    assert types["notas_fiscais"]["chave"] == "text"
    assert specs["clientes"].key_columns == ["codigo"]
    assert specs["eventos"].dedup == "row_hash"
    assert specs["transacoes"].materialization == "incremental"
    assert types["trajetoria"]["co_curso"] == "text"
    assert types["trajetoria"]["qt_ingressante"] == "bigint"
    assert types["trajetoria"]["tda"] == "numeric"
    assert types["microdados_cadastro_cursos"]["co_curso"] == "text"
    assert types["microdados_cadastro_cursos"]["qt_mat"] == "bigint"
    assert "ERROR=0" in out

    gold = f"gold.{prefix}"
    assert _query(s, f"SELECT count(*), count(DISTINCT codigo) FROM {gold}clientes") == [(60, 60)]
    assert _query(s, f"SELECT count(*) FROM {gold}clientes WHERE e_mail_hash LIKE '%%@%%'") == [
        (0,)
    ]
    assert _query(s, f"SELECT count(*) FROM {gold}eventos") == [(3,)]
    assert _query(s, f"SELECT valor::text AS v FROM {gold}export_erp ORDER BY valor") == [
        ("89.90",),
        ("1500.00",),
    ]

    (inbox / f"{prefix}clientes" / "clientes_2026_03.csv").write_text(
        "Código;Renda Mensal;Score\n001;abc;870\n", encoding="utf-8"
    )
    _, specs2, out2 = _cycle(s, prefix)
    types2 = {c.output_name: c.inferred_type for c in specs2["clientes"].columns}
    assert types2["renda_mensal"] == "numeric"
    assert types2["score"] == "bigint"
    assert "WARN=1" in out2 and "dh_invalid_ratio" in out2
    assert _query(
        s, f"SELECT renda_mensal, score FROM silver.{prefix}clientes WHERE codigo = '001'"
    ) == [(None, 870)]
    assert _query(s, f"SELECT count(*) FROM {gold}clientes") == [(60,)]


def test_inep_flow_to_outputs_with_small_cell_suppression(auto_env):
    s, _, prefix, project = auto_env
    bi_password = os.environ.get("WAREHOUSE_BI_PASSWORD")
    if not bi_password:
        pytest.skip("WAREHOUSE_BI_PASSWORD ausente")
    mart = f"{prefix}mart_coorte"
    (project / "models" / "gold" / f"{mart}.sql").write_text(
        "select co_curso, nu_ano_ingresso, max(qt_ingressante) as qt_ingressante,\n"
        "       max(qt_desistencia) as qt_desistencia\n"
        f"from {{{{ ref('auto_silver__{prefix}trajetoria') }}}}\n"
        "group by co_curso, nu_ano_ingresso\n",
        encoding="utf-8",
    )
    _cycle(s, prefix, (mart,))
    assert _query(s, f"SELECT count(*) FROM silver.{prefix}trajetoria") == [(114,)]
    assert _query(s, f"SELECT count(*) FROM silver.{prefix}microdados_cadastro_cursos") == [(12,)]
    coverage = _query(
        s,
        f"SELECT count(DISTINCT t.co_curso), count(DISTINCT c.co_curso) "
        f"FROM silver.{prefix}trajetoria t "
        f"LEFT JOIN silver.{prefix}microdados_cadastro_cursos c USING (co_curso)",
    )
    assert coverage == [(6, 6)]

    out = s.dbt_project_dir.parent / "outputs"
    settings_bi = dataclasses.replace(s, export_password=bi_password)
    config = ExportConfig.model_validate({"tables": [{"name": mart}]})
    manifest = Exporter(settings_bi.export_conninfo(), out, config).run()
    table = manifest["tables"][0]
    total = _query(s, f"SELECT count(*) FROM gold.{mart}")[0][0]
    assert table["base_columns"] == ["qt_ingressante"]
    assert table["rows"] + table["suppressed_rows"] == total
    lines = (out / f"{mart}.csv").read_text(encoding="utf-8").splitlines()[1:]
    assert lines and all(int(line.split(",")[2]) >= 10 for line in lines)
