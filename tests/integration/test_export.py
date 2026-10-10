from __future__ import annotations

import dataclasses
import json
import os

import psycopg
import pyarrow.parquet as pq
import pytest

from datahack_ingest.export import ExportConfig, Exporter, ExportError

pytestmark = pytest.mark.integration


@pytest.fixture
def gold_table(settings, unique_name):
    password = os.environ.get("WAREHOUSE_DBT_PASSWORD")
    if not password or not os.environ.get("WAREHOUSE_BI_PASSWORD"):
        pytest.skip("credenciais dbt/bi ausentes")
    dbt = psycopg.conninfo.make_conninfo(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_db,
        user=os.environ.get("WAREHOUSE_DBT_USER", "dh_transformer"),
        password=password,
    )
    with psycopg.connect(dbt, autocommit=True) as c:
        c.execute(
            f"""CREATE TABLE gold.{unique_name} AS
                SELECT * FROM (VALUES
                    ('001'::text, 120::bigint, 35.5::numeric, '{{"a": 1}}'::jsonb),
                    ('002', 8, 12.0, null),
                    ('003', null, 1.0, null)
                ) v(co_curso, qt_ingressante, tda, extra)"""
        )
        c.execute(f"GRANT SELECT ON gold.{unique_name} TO dh_bi_reader")
    yield unique_name
    with psycopg.connect(dbt, autocommit=True) as c:
        c.execute(f"DROP TABLE IF EXISTS gold.{unique_name}")


def test_export_suppresses_small_cells_and_writes_manifest(settings, gold_table, tmp_path):
    s = dataclasses.replace(settings, export_password=os.environ["WAREHOUSE_BI_PASSWORD"])
    config = ExportConfig.model_validate({"tables": [{"name": gold_table}]})
    manifest = Exporter(s.export_conninfo(), tmp_path, config).run()
    table = manifest["tables"][0]
    assert (table["rows"], table["suppressed_rows"]) == (1, 2)
    assert table["base_columns"] == ["qt_ingressante"]
    assert (tmp_path / f"{gold_table}.csv").read_text(encoding="utf-8").splitlines() == [
        "co_curso,qt_ingressante,tda,extra",
        '001,120,35.5,"{""a"": 1}"',
    ]
    assert pq.read_table(tmp_path / f"{gold_table}.parquet").to_pylist()[0]["co_curso"] == "001"
    saved = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert {f["file"] for f in saved["tables"][0]["files"]} == {
        f"{gold_table}.csv",
        f"{gold_table}.parquet",
    }
    first = (tmp_path / f"{gold_table}.csv").read_bytes()
    Exporter(s.export_conninfo(), tmp_path, config).run()
    assert (tmp_path / f"{gold_table}.csv").read_bytes() == first


def test_export_refuses_table_without_base_column(settings, gold_table, tmp_path):
    s = dataclasses.replace(settings, export_password=os.environ["WAREHOUSE_BI_PASSWORD"])
    bad = ExportConfig.model_validate(
        {"tables": [{"name": gold_table, "min_cell_column": "nao_existe"}]}
    )
    with pytest.raises(ExportError, match="min_cell_column"):
        Exporter(s.export_conninfo(), tmp_path, bad).run()
    assert not list(tmp_path.iterdir())
