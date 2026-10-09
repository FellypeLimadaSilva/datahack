import json

import pytest

from datahack_ingest.cli import main


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DH_EXAMPLES", "false")
    monkeypatch.setenv("DH_LANDING_URI", str(tmp_path / "landing"))
    monkeypatch.setenv("DH_INBOX_SETTLE_SECONDS", "0")


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


def test_validate_reports_missing_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TOKEN_X", raising=False)
    extra = (
        "  - name: api_x\n    kind: api\n"
        "    api: { url: 'https://x', auth: { type: bearer, token_env: TOKEN_X } }\n"
    )
    assert main(["--catalog", _catalog(tmp_path, extra), "validate"]) == 2
    assert "TOKEN_X" in capsys.readouterr().err


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


def _inbox(tmp_path):
    inbox = tmp_path / "landing" / "inbox"
    (inbox / "vendas").mkdir(parents=True)
    (inbox / "vendas" / "jan.csv").write_text("id;valor\n1;10,5\n", encoding="utf-8")
    (inbox / "manual.pdf").write_bytes(b"%PDF")
    return inbox


def test_discover_and_list_show_inbox_sources(tmp_path, capsys):
    cat = _catalog(tmp_path)
    _inbox(tmp_path)
    assert main(["--catalog", cat, "discover", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [s["name"] for s in report["sources"]] == ["vendas"]
    assert report["ignored"][0]["reason"] == "não é dado tabular"
    assert main(["--catalog", cat, "list", "--json"]) == 0
    origins = {s["name"]: s["origin"] for s in json.loads(capsys.readouterr().out)}
    assert origins == {"clientes": "catalog", "vendas": "inbox"}
    assert main(["--catalog", cat, "list"]) == 0
    assert "inbox" in capsys.readouterr().out


def test_run_all_reports_inbox_errors_and_continues(tmp_path, capsys):
    cat = _catalog(tmp_path)
    inbox = _inbox(tmp_path)
    (inbox / "vendas" / "_source.yml").write_text("kind: sql\n", encoding="utf-8")
    assert main(["--catalog", cat, "validate"]) == 2
    capsys.readouterr()
    assert main(["--catalog", cat, "run", "--all", "--dry-run", "--continue-on-error"]) == 1
    results = json.loads(capsys.readouterr().out)
    assert results[0]["status"] == "failed" and "kind" in results[0]["error"]
    assert results[1]["source"] == "clientes" and results[1]["status"] == "dry_run"


def test_generate_models_can_be_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DH_AUTO_MODELS", "false")
    assert main(["--catalog", _catalog(tmp_path), "generate-models"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "disabled"


def test_invalid_flag_value_is_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DH_EXAMPLES", "talvez")
    assert main(["--catalog", _catalog(tmp_path), "list"]) == 2
    assert "DH_EXAMPLES" in capsys.readouterr().err
