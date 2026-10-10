import json

import pytest

from datahack_ingest.cli import main


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DH_LANDING_URI", str(tmp_path / "landing"))


def _catalog(tmp_path, extra: str = "") -> str:
    (tmp_path / "landing").mkdir()
    (tmp_path / "landing" / "a.csv").write_text("ID Cliente,Nome\n1,Ana\n2,Bia\n", encoding="utf-8")
    cat = tmp_path / "sources.yml"
    cat.write_text(
        "version: 1\nsources:\n"
        "  - name: clientes\n    kind: file\n    file: { path: a.csv, format: csv }\n" + extra,
        encoding="utf-8",
    )
    return str(cat)


def test_list_json(tmp_path, capsys):
    assert main(["--catalog", _catalog(tmp_path), "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "clientes"


def test_invalid_catalog_exit_code_2(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("version: 1\nsources:\n  - name: X Y\n    kind: file\n", encoding="utf-8")
    assert main(["--catalog", str(bad), "list"]) == 2


def test_dry_run_profiles_without_database(tmp_path, monkeypatch, capsys):
    cat = _catalog(tmp_path)
    monkeypatch.setenv("DH_LANDING_URI", str(tmp_path / "landing"))
    assert main(["--catalog", cat, "run", "clientes", "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)[0]
    assert out["status"] == "dry_run"
    assert out["rows_extracted"] == 2
    assert out["columns"] == ["id_cliente", "nome"]


def test_run_requires_sources_or_all(tmp_path):
    assert main(["--catalog", _catalog(tmp_path), "run"]) == 2


def test_list_marks_required_and_optional(tmp_path, capsys):
    extra = (
        "  - name: extra\n    kind: file\n    required: false\n"
        "    file: { path: a.csv, format: csv }\n"
    )
    assert main(["--catalog", _catalog(tmp_path, extra), "list"]) == 0
    out = capsys.readouterr().out
    assert "clientes" in out and "obrigatória" in out and "opcional" in out


def test_publish_without_dbt_results_is_rejected_offline(tmp_path):
    from datahack_ingest.publish import dbt_gate

    report = dbt_gate(tmp_path / "run_results.json", 0)
    assert not report.ok
    assert "run_results" in report.problems[0]


def test_validate_lists_files_and_warns_on_missing_required(tmp_path, capsys):
    extra = (
        "  - name: falta\n    kind: file\n"
        "    file: { path: nada, include: ['*.csv'], format: csv }\n"
    )
    assert main(["--catalog", _catalog(tmp_path, extra), "validate"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report[0]["files"] == ["a.csv"]
    assert "falta" in captured.err
