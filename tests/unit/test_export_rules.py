import json

from datahack_ingest.export import indicator_metadata, small_cells
from datahack_ingest.publish import dbt_gate


def test_small_cells_flags_only_student_counts_between_1_and_9():
    names = ["co_curso", "qt_ingressante", "qt_desistencia", "nu_cursos"]
    rows = [("1", 120, 0, 3), ("2", 50, None, 1), ("3", 40, 9, 2)]
    assert small_cells(rows, names, 10) == ["qt_desistencia"]
    assert small_cells(rows[:2], names, 10) == []


def test_indicator_metadata_reads_model_meta(tmp_path):
    manifest = {
        "nodes": {
            "model.datahack.p1": {
                "resource_type": "model",
                "name": "p1",
                "description": "P1",
                "meta": {"denominador": "ingressantes"},
                "columns": {"taxa": {"description": "%", "meta": {}}},
            },
            "model.datahack.outro": {"resource_type": "model", "name": "outro"},
        }
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    meta = indicator_metadata(path, ["p1"])
    assert list(meta) == ["p1"]
    assert meta["p1"]["meta"]["denominador"] == "ingressantes"


def test_dbt_gate_blocks_on_failed_or_skipped_nodes(tmp_path):
    results = {
        "metadata": {"invocation_id": "x"},
        "results": [
            {"unique_id": "model.a", "status": "success"},
            {"unique_id": "test.b", "status": "warn"},
            {"unique_id": "model.c", "status": "skipped"},
        ],
    }
    path = tmp_path / "run_results.json"
    path.write_text(json.dumps(results), encoding="utf-8")
    report = dbt_gate(path, 1)
    assert not report.ok
    assert report.problems == ["model.c: skipped"]
    assert report.detail["warnings"] == ["test.b"]
    results["results"].pop()
    path.write_text(json.dumps(results), encoding="utf-8")
    assert dbt_gate(path, 0).ok
