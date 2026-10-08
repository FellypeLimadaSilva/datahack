from pathlib import Path

import pytest
from pydantic import ValidationError

from datahack_ingest.catalog import Catalog, load_catalog, required_env_vars

ROOT = Path(__file__).resolve().parents[2]


def test_repository_catalog_is_valid():
    cat = load_catalog(ROOT / "config" / "sources.yml")
    names = [s.name for s in cat.enabled()]
    assert {"lojas", "produtos", "vendas", "metas", "estoque_foto"} <= set(names)


def _src(**over):
    base = {"name": "x", "kind": "file", "file": {"path": "a.csv", "format": "csv"}}
    base.update(over)
    return base


def test_merge_requires_primary_key():
    with pytest.raises(ValidationError, match="primary_key"):
        Catalog.model_validate({"sources": [_src(load_strategy="merge")]})


def test_parquet_sink_rejects_merge():
    with pytest.raises(ValidationError, match="parquet"):
        Catalog.model_validate(
            {"sources": [_src(load_strategy="merge", primary_key=["id"], sink="parquet")]}
        )


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


def test_sql_requires_exactly_one_of_query_or_table():
    with pytest.raises(ValidationError):
        Catalog.model_validate(
            {
                "sources": [
                    {
                        "name": "s",
                        "kind": "sql",
                        "sql": {"url_env": "X", "query": "select 1", "table": "t"},
                    }
                ]
            }
        )


def test_required_env_vars_for_api_and_sql():
    cat = Catalog.model_validate(
        {
            "sources": [
                {
                    "name": "a",
                    "kind": "api",
                    "api": {"url": "https://x", "auth": {"type": "bearer", "token_env": "TOK"}},
                },
                {"name": "s", "kind": "sql", "sql": {"url_env": "DB_URL", "table": "t"}},
            ]
        }
    )
    assert required_env_vars(cat.get("a")) == ["TOK"]
    assert required_env_vars(cat.get("s")) == ["DB_URL"]
