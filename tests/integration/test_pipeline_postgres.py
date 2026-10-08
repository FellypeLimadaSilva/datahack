from __future__ import annotations

import dataclasses

import psycopg
import pytest
from psycopg import sql

from datahack_ingest.catalog import Catalog
from datahack_ingest.runner import SourceLockedError, run_source
from datahack_ingest.state import StateStore

pytestmark = pytest.mark.integration


def _file_source(name: str, path: str, **over):
    spec = {
        "name": name,
        "kind": "file",
        "chunk_size": 100,
        "file": {"path": path, "format": "csv"},
    }
    spec.update(over)
    return Catalog.model_validate({"sources": [spec]}).sources[0]


@pytest.fixture
def env(settings, tmp_path, unique_name):
    s = dataclasses.replace(settings, landing_uri=str(tmp_path))
    yield s, tmp_path, unique_name
    with psycopg.connect(s.conninfo(), autocommit=True) as c:
        c.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier("bronze", unique_name)))
        for t in (
            "ingestion_runs",
            "watermarks",
            "file_manifest",
            "schema_changes",
            "rejected_rows",
        ):
            c.execute(
                sql.SQL("DELETE FROM {} WHERE source = %s").format(sql.Identifier("ops", t)),
                (unique_name,),
            )


def _rows(s, query: str, *params):
    with psycopg.connect(s.conninfo()) as c:
        return c.execute(query, params).fetchall()


def test_merge_upserts_rejects_null_pk_and_is_idempotent(env):
    s, d, name = env
    (d / "a.csv").write_text("id,valor\n1,10\n2,20\n,99\n", encoding="utf-8")
    src = _file_source(name, "*.csv", load_strategy="merge", primary_key=["id"])
    r1 = run_source(src, s)
    assert (r1.rows_loaded, r1.rows_rejected) == (2, 1)

    (d / "b.csv").write_text("id,valor\n1,10\n2,25\n3,30\n", encoding="utf-8")
    r2 = run_source(src, s)
    assert r2.units_skipped == 1 and r2.rows_loaded == 2
    data = _rows(s, f'SELECT id, valor FROM bronze."{name}" ORDER BY id::int')
    assert data == [("1", "10"), ("2", "25"), ("3", "30")]

    r3 = run_source(src, s)
    assert r3.units_processed == 0 and r3.units_skipped == 2


def test_full_replaces_atomically_and_schema_drift_is_audited(env):
    s, d, name = env
    f = d / "c.csv"
    f.write_text("id\n1\n2\n", encoding="utf-8")
    src = _file_source(name, "c.csv", load_strategy="full")
    run_source(src, s)
    f.write_text("id,nova_coluna\n3,x\n", encoding="utf-8")
    r = run_source(src, s)
    assert r.new_columns == ["nova_coluna"]
    assert _rows(s, f'SELECT id, nova_coluna FROM bronze."{name}"') == [("3", "x")]
    changes = _rows(s, "SELECT column_name FROM ops.schema_changes WHERE source = %s", name)
    assert ("nova_coluna",) in changes


def test_failure_rolls_back_and_is_recorded(env):
    s, d, name = env
    (d / "ok.csv").write_text("id\n1\n", encoding="utf-8")
    src = _file_source(name, "ok.csv", load_strategy="merge", primary_key=["id_inexistente"])
    with pytest.raises(ValueError, match="primary_key ausente"):
        run_source(src, s)
    status = _rows(
        s, "SELECT status, error IS NOT NULL FROM ops.ingestion_runs WHERE source = %s", name
    )
    assert status == [("failed", True)]
    assert _rows(s, "SELECT count(*) FROM ops.file_manifest WHERE source = %s", name) == [(0,)]


def test_concurrent_run_is_blocked_by_advisory_lock(env):
    s, d, name = env
    (d / "x.csv").write_text("id\n1\n", encoding="utf-8")
    src = _file_source(name, "x.csv")
    with psycopg.connect(s.conninfo(), autocommit=True) as holder:
        assert StateStore(holder).try_lock(name)
        with pytest.raises(SourceLockedError):
            run_source(src, s)


def test_ingestor_cannot_read_gold_or_silver(settings):
    with psycopg.connect(settings.conninfo(), autocommit=True) as c:
        for schema in ("silver", "gold"):
            row = c.execute(
                "SELECT has_schema_privilege(current_user, %s, 'USAGE')", (schema,)
            ).fetchone()
            assert row == (False,), f"dh_ingestor não deveria acessar {schema}"


def test_parquet_sink_writes_partitioned_lake(env, tmp_path_factory):
    s, d, name = env
    lake = tmp_path_factory.mktemp("lake")
    s = dataclasses.replace(s, lake_uri=str(lake))
    (d / "e.csv").write_text("id,evento\n1,click\n2,view\n", encoding="utf-8")
    src = _file_source(name, "e.csv", sink="parquet", load_strategy="append")
    r = run_source(src, s)
    assert r.rows_loaded == 2
    files = list((lake / "bronze" / name).rglob("*.parquet"))
    assert len(files) == 1 and files[0].parent.name.startswith("ingest_date=")
    import pyarrow.parquet as pq

    t = pq.read_table(files[0])
    assert t.column("evento").to_pylist() == ["click", "view"]
    assert "_dh_row_hash" in t.column_names
