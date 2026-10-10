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


def test_append_loads_each_file_once_and_rerun_is_noop(env):
    s, d, name = env
    (d / "a_2021.csv").write_text("ano,v\n2021,10\n2021,20\n", encoding="utf-8")
    src = _file_source(name, "*.csv", load_strategy="append")
    r1 = run_source(src, s)
    assert (r1.units_processed, r1.rows_loaded) == (1, 2)
    (d / "a_2023.csv").write_text("ano,v\n2023,30\n", encoding="utf-8")
    r2 = run_source(src, s)
    assert (r2.units_processed, r2.units_skipped, r2.rows_loaded) == (1, 1, 1)
    r3 = run_source(src, s)
    assert (r3.units_processed, r3.rows_loaded) == (0, 0)
    years = _rows(s, f'SELECT ano, count(*) FROM bronze."{name}" GROUP BY ano ORDER BY ano')
    assert years == [("2021", 2), ("2023", 1)]


def test_full_with_many_files_keeps_all_of_them(env):
    s, d, name = env
    for year in (2021, 2022, 2023):
        (d / f"p_{year}.csv").write_text(f"ano\n{year}\n", encoding="utf-8")
    src = _file_source(name, "p_*.csv", load_strategy="full")
    run_source(src, s)
    run_source(src, s)
    assert _rows(s, f'SELECT ano FROM bronze."{name}" ORDER BY ano') == [
        ("2021",),
        ("2022",),
        ("2023",),
    ]


def test_missing_essential_column_rolls_back_the_file(env):
    s, d, name = env
    (d / "a.csv").write_text("id,valor\n1,10\n", encoding="utf-8")
    src = _file_source(name, "a.csv", essential_columns=["id", "qt_ingressante"])
    with pytest.raises(Exception, match="colunas essenciais"):
        run_source(src, s)
    status = _rows(
        s, "SELECT status, error IS NOT NULL FROM ops.ingestion_runs WHERE source = %s", name
    )
    assert status == [("failed", True)]
    assert _rows(s, "SELECT count(*) FROM ops.file_manifest WHERE source = %s", name) == [(0,)]
    exists = _rows(s, "SELECT to_regclass(%s) IS NULL", f"bronze.{name}")
    count = (0,) if exists == [(True,)] else _rows(s, f'SELECT count(*) FROM bronze."{name}"')[0]
    assert count == (0,)


def test_empty_full_load_keeps_previous_version(env):
    s, d, name = env
    f = d / "c.csv"
    f.write_text("id\n1\n2\n", encoding="utf-8")
    src = _file_source(
        name,
        "c.csv",
        load_strategy="full",
        transforms=[{"op": "filter", "column": "id", "operator": "ne", "value": "x"}],
    )
    run_source(src, s)
    f.write_text("id\nx\n", encoding="utf-8")
    with pytest.raises(Exception, match="sem linhas"):
        run_source(src, s)
    assert _rows(s, f'SELECT id FROM bronze."{name}" ORDER BY id') == [("1",), ("2",)]


def _write_ids(path, ids):
    path.write_text("id,nome\n" + "".join(f"{i},n{i}\n" for i in ids), encoding="utf-8")


def test_volume_check_fail_blocks_full_reload(env):
    s, d, name = env
    src = _file_source(
        name,
        "c.csv",
        load_strategy="full",
        volume_check={"lookback_runs": 5, "min_history": 3, "min_ratio": 0.5, "action": "fail"},
    )
    for _ in range(3):
        _write_ids(d / "c.csv", range(1, 101))
        run_source(src, s)
    _write_ids(d / "c.csv", range(1, 6))
    with pytest.raises(Exception, match="volume fora do esperado"):
        run_source(src, s)
    assert _rows(s, f'SELECT count(*) FROM bronze."{name}"') == [(100,)]
    events = _rows(
        s, "SELECT check_name, severity FROM ops.data_quality_events WHERE source = %s", name
    )
    assert events == [("volume", "error")]
    with psycopg.connect(s.conninfo(), autocommit=True) as c:
        c.execute("DELETE FROM ops.data_quality_events WHERE source = %s", (name,))


def test_etl_transforms_before_load(env, monkeypatch):
    s, d, name = env
    monkeypatch.setenv("DBT_PII_SALT", "salt")
    (d / "c.csv").write_text(
        "id,cpf,status,cartao\n1,111.222.333-44,ativo,4111111111111111\n2,555,inativo,1\n",
        encoding="utf-8",
    )
    src = _file_source(
        name,
        "c.csv",
        load_strategy="full",
        transforms=[
            {"op": "filter", "column": "status", "operator": "eq", "value": "ativo"},
            {"op": "hash_columns", "columns": ["cpf"], "digits_only": True},
            {"op": "mask_columns", "columns": ["cartao"], "keep_last": 4},
            {"op": "drop_columns", "columns": ["status"]},
        ],
    )
    r = run_source(src, s)
    assert (r.rows_extracted, r.rows_filtered, r.rows_loaded) == (2, 1, 1)
    row = _rows(s, f'SELECT cpf, cartao FROM bronze."{name}"')[0]
    assert len(row[0]) == 64 and "111" not in row[0]
    assert row[1] == "************1111"
    cols = {
        r[0]
        for r in _rows(
            s, "SELECT column_name FROM information_schema.columns WHERE table_name = %s", name
        )
    }
    assert "status" not in cols
    assert _rows(s, "SELECT rows_filtered FROM ops.ingestion_runs WHERE source = %s", name) == [
        (1,)
    ]
