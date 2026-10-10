from pathlib import Path

import pytest
from pydantic import ValidationError

from datahack_ingest.catalog import Catalog, load_catalog, required_env_vars

ROOT = Path(__file__).resolve().parents[2]


def test_repository_catalogs_are_valid():
    templates = load_catalog(ROOT / "config" / "sources.yml")
    assert {s.name for s in templates.enabled()} == {
        "censo_cursos",
        "censo_ies",
        "trajetoria",
        "cpc",
        "igc",
        "enade_licenciaturas",
        "ibge_populacao_idade_mt",
    }
    required = {s.name for s in templates.enabled() if s.required}
    assert required == {"censo_cursos", "censo_ies", "trajetoria", "cpc"}
    assert all(s.essential_columns for s in templates.enabled() if s.required)


def _src(**over):
    base = {"name": "x", "kind": "file", "file": {"path": "a.csv", "format": "csv"}}
    base.update(over)
    return base


def test_only_full_and_append_strategies():
    with pytest.raises(ValidationError):
        Catalog.model_validate({"sources": [_src(load_strategy="merge")]})
    with pytest.raises(ValidationError):
        Catalog.model_validate({"sources": [_src(kind="sql", sql={"url": "sqlite:///x"})]})


def test_invalid_identifier_rejected():
    with pytest.raises(ValidationError):
        Catalog.model_validate({"sources": [_src(name="Nome Inválido")]})


def test_unknown_field_rejected_typo_protection():
    with pytest.raises(ValidationError):
        Catalog.model_validate({"sources": [_src(load_stratgy="full")]})


def test_duplicate_target_table_rejected():
    with pytest.raises(ValidationError, match="duplicada"):
        Catalog.model_validate(
            {"sources": [_src(name="a", target_table="t"), _src(name="b", target_table="t")]}
        )


def test_required_env_vars_for_api():
    cat = Catalog.model_validate(
        {
            "sources": [
                {
                    "name": "a",
                    "kind": "api",
                    "api": {"url": "https://x", "auth": {"type": "bearer", "token_env": "TOK"}},
                },
            ]
        }
    )
    assert required_env_vars(cat.get("a")) == ["TOK"]
