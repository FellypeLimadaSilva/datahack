from __future__ import annotations

import csv
import dataclasses
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import psycopg
import pytest
import yaml

from datahack_ingest.cli import main
from datahack_ingest.state import StateStore

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
DBT = shutil.which("dbt") or str(Path(sys.executable).with_name("dbt"))


def _fixtures():
    spec = importlib.util.spec_from_file_location(
        "generate_inep_fixtures", ROOT / "scripts" / "generate_inep_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def rota(settings, tmp_path, monkeypatch):
    if os.environ.get("DH_E2E") != "true":
        pytest.skip("DH_E2E=true liga o teste ponta a ponta (recria bronze, silver e gold)")
    if not Path(DBT).exists():
        pytest.skip("dbt não instalado")
    for var in ("WAREHOUSE_DBT_PASSWORD", "WAREHOUSE_BI_PASSWORD"):
        if not os.environ.get(var):
            pytest.skip(f"{var} ausente")
    landing = tmp_path / "landing"
    fx = _fixtures()
    fx.main(["--out", str(landing)])
    raw = yaml.safe_load((ROOT / "config" / "sources.yml").read_text(encoding="utf-8"))
    raw["sources"] = [s for s in raw["sources"] if s["kind"] == "file"]
    catalog = tmp_path / "sources.yml"
    catalog.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("DH_LANDING_URI", str(landing))
    monkeypatch.setenv("DH_OUTPUTS", str(outputs))
    monkeypatch.setenv("DBT_PROFILES_DIR", str(ROOT / "dbt"))
    monkeypatch.setenv("DBT_PROJECT_DIR", str(ROOT / "dbt"))
    monkeypatch.chdir(ROOT)
    s = dataclasses.replace(
        settings,
        transform_password=os.environ["WAREHOUSE_DBT_PASSWORD"],
        export_password=os.environ["WAREHOUSE_BI_PASSWORD"],
    )
    _reset(s, [src["name"] for src in raw["sources"]])
    return s, fx, landing, str(catalog), outputs


def _reset(s, sources: list[str]) -> None:
    with psycopg.connect(s.conninfo(), autocommit=True) as c:
        StateStore(c).ensure()
        for name in sources:
            c.execute(f"DROP TABLE IF EXISTS bronze.{name}")
        for table in ("ingestion_runs", "file_manifest", "schema_changes", "data_quality_events"):
            c.execute(f"DELETE FROM ops.{table} WHERE source = ANY(%s)", (sources,))
    with psycopg.connect(s.transform_conninfo(), autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS gold_previous CASCADE")


def _pipeline(catalog: str, capsys) -> tuple[int, dict]:
    code = main(["--catalog", catalog, "pipeline"])
    out = capsys.readouterr().out
    return code, json.loads(out[out.index("{") :])


def _gold(s, query: str):
    with psycopg.connect(s.export_conninfo()) as c:
        return c.execute(query).fetchall()


def _version(s) -> str | None:
    with psycopg.connect(s.transform_conninfo()) as c:
        row = c.execute("SELECT obj_description('gold'::regnamespace, 'pg_namespace')").fetchone()
    return row[0].rsplit(": ", 1)[1] if row and row[0] else None


def _csv(outputs: Path, name: str) -> list[dict]:
    with (outputs / f"{name}.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_rota_do_diploma_ponta_a_ponta(rota, capsys):
    s, fx, landing, catalog, outputs = rota

    code, run1 = _pipeline(catalog, capsys)
    assert code == 0, run1
    assert run1["publication"]["status"] == "published"
    v1 = run1["version"]
    assert _version(s) == v1

    expected = {}
    for coorte in (2019, 2020):
        rows = [r for r in fx.trajetoria_rows(coorte, 1) if r[7] == "51"]
        expected[coorte] = sum(r[21] for r in rows if r[16] == coorte)
    p1 = _gold(
        s,
        "SELECT nu_ano_ingresso, qt_ingressante FROM p1_trajetoria_coorte "
        "WHERE nu_ano_referencia = nu_ano_ingresso ORDER BY 1",
    )
    assert p1 == [(2019, expected[2019]), (2020, expected[2020])]
    censo = _gold(s, "SELECT DISTINCT nu_ano_censo FROM p3_rede_modalidade_ano ORDER BY 1")
    assert censo == [(2021,), (2023,)]
    assert _gold(s, "SELECT count(*), count(DISTINCT co_curso) FROM p4_qualidade_curso") == [(6, 6)]

    manifest = json.loads((outputs / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == v1
    assert manifest["sources"]["trajetoria"]["files"]
    indicators = json.loads((outputs / "_indicadores.json").read_text(encoding="utf-8"))
    assert indicators["p1_trajetoria_coorte"]["meta"]["denominador"]
    for table in manifest["tables"]:
        name = table["table"].split(".", 1)[1]
        for row in _csv(outputs, name):
            for key, value in row.items():
                if key.startswith("qt_") and value:
                    assert not 0 < int(value) < 10, (name, key, value)
    hashes = {
        f["file"]: f["sha256"]
        for t in manifest["tables"]
        if t["table"] != "gold.controle_atualizacao"
        for f in t["files"]
    }

    code, run2 = _pipeline(catalog, capsys)
    assert code == 0 and all(r["rows_loaded"] == 0 for r in run2["ingest"])
    manifest2 = json.loads((outputs / "_manifest.json").read_text(encoding="utf-8"))
    hashes2 = {
        f["file"]: f["sha256"]
        for t in manifest2["tables"]
        if t["table"] != "gold.controle_atualizacao"
        for f in t["files"]
    }
    assert hashes2 == hashes

    fx.write_trajetoria(landing, 2020, seed=2)
    code, run3 = _pipeline(catalog, capsys)
    assert code == 0, run3
    revised = sum(r[21] for r in fx.trajetoria_rows(2020, 2) if r[7] == "51" and r[16] == 2020)
    p1 = _gold(
        s,
        "SELECT nu_ano_ingresso, qt_ingressante FROM p1_trajetoria_coorte "
        "WHERE nu_ano_referencia = nu_ano_ingresso ORDER BY 1",
    )
    assert p1 == [(2019, expected[2019]), (2020, revised)]
    v3 = run3["version"]

    fx.write_trajetoria(landing, 2018, invalid=True)
    code, run4 = _pipeline(catalog, capsys)
    assert code == 1
    assert run4["publication"]["status"] == "rejected"
    assert run4["publication"]["kept"] == v3
    assert _version(s) == v3
    assert json.loads((outputs / "_manifest.json").read_text(encoding="utf-8"))["version"] == v3

    fx.write_cpc(landing, 2023, drop="CPC (Faixa)")
    code, run5 = _pipeline(catalog, capsys)
    assert code == 1
    fontes = next(c for c in run5["checks"] if c["stage"] == "fontes")
    assert not fontes["ok"] and any("cpc" in p for p in fontes["problems"])
    assert _version(s) == v3

    (landing / "inep" / "qualidade" / "cpc_2023.xlsx").unlink()
    fx.write_trajetoria(landing, 2018)
    code, run6 = _pipeline(catalog, capsys)
    assert code == 0, run6
    assert _gold(s, "SELECT count(*) FROM p1_trajetoria_coorte WHERE nu_ano_ingresso = 2018")[0][0]

    assert main(["--catalog", catalog, "rollback"]) == 0
    assert json.loads(capsys.readouterr().out)["to"] == v3
    assert _version(s) == v3

    with psycopg.connect(s.export_conninfo()) as c:
        for schema in ("gold_candidate", "gold_previous", "silver", "bronze"):
            row = c.execute("SELECT has_schema_privilege(%s, 'USAGE')", (schema,)).fetchone()
            assert row == (False,), schema
