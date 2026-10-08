import hashlib

import pandas as pd
import pytest
from pydantic import ValidationError

from datahack_ingest.catalog import Catalog
from datahack_ingest.transforms import TransformError, apply_transforms


def double_valor(df: pd.DataFrame) -> pd.DataFrame:
    df["valor_dobro"] = [str(int(v) * 2) if v else None for v in df["valor"]]
    return df


def _steps(*steps):
    spec = {
        "name": "x",
        "kind": "file",
        "file": {"path": "a.csv", "format": "csv"},
        "transforms": list(steps),
    }
    return Catalog.model_validate({"sources": [spec]}).sources[0].transforms


def _frame():
    return pd.DataFrame(
        {
            "id": ["1", "2", "3", "4"],
            "cpf": ["123.456.789-01", None, "98765432100", "11122233344"],
            "nome": [" Ana ", "bia", "Caio", None],
            "valor": ["10", "250", "-5", None],
            "uf": ["MT", "SP", "MT", "GO"],
        },
        dtype=object,
    )


def test_hash_matches_dbt_algorithm(monkeypatch):
    monkeypatch.setenv("DBT_PII_SALT", "s4lt")
    out = apply_transforms(
        _frame(), _steps({"op": "hash_columns", "columns": ["cpf"], "digits_only": True})
    )
    expected = hashlib.sha256(b"s4lt12345678901").hexdigest()
    assert out["cpf"].tolist()[0] == expected
    assert out["cpf"].tolist()[1] is None


def test_hash_requires_salt(monkeypatch):
    monkeypatch.delenv("DBT_PII_SALT", raising=False)
    with pytest.raises(TransformError, match="DBT_PII_SALT"):
        apply_transforms(_frame(), _steps({"op": "hash_columns", "columns": ["cpf"]}))


def test_mask_keeps_last_digits():
    out = apply_transforms(
        _frame(), _steps({"op": "mask_columns", "columns": ["cpf"], "keep_last": 2})
    )
    assert out["cpf"].tolist()[0] == "************01"
    assert out["cpf"].tolist()[1] is None


@pytest.mark.parametrize(
    ("step", "expected_ids"),
    [
        ({"op": "filter", "column": "uf", "operator": "eq", "value": "MT"}, ["1", "3"]),
        ({"op": "filter", "column": "uf", "operator": "in", "value": ["SP", "GO"]}, ["2", "4"]),
        ({"op": "filter", "column": "valor", "operator": "gt", "value": 0}, ["1", "2"]),
        ({"op": "filter", "column": "valor", "operator": "lte", "value": 10}, ["1", "3"]),
        ({"op": "filter", "column": "nome", "operator": "not_null"}, ["1", "2", "3"]),
        ({"op": "filter", "column": "cpf", "operator": "regex", "value": r"^\d{11}$"}, ["3", "4"]),
    ],
)
def test_filter_operators(step, expected_ids):
    assert apply_transforms(_frame(), _steps(step))["id"].tolist() == expected_ids


def test_chain_drop_rename_trim_constant_dedup():
    df = pd.concat([_frame(), _frame().head(1)], ignore_index=True)
    out = apply_transforms(
        df,
        _steps(
            {"op": "deduplicate", "keys": ["id"]},
            {"op": "drop_columns", "columns": ["cpf"]},
            {"op": "rename", "mapping": {"uf": "estado"}},
            {"op": "trim", "columns": ["nome"]},
            {"op": "upper", "columns": ["nome"]},
            {"op": "add_constant", "column": "origem", "value": "erp"},
        ),
    )
    assert len(out) == 4
    assert "cpf" not in out.columns and "estado" in out.columns
    by_id = dict(zip(out["id"], out["nome"], strict=True))
    assert (by_id["1"], by_id["2"], by_id["3"], by_id["4"]) == ("ANA", "BIA", "CAIO", None)
    assert set(out["origem"]) == {"erp"}


def test_select_unknown_column_fails_with_context():
    with pytest.raises(TransformError, match="inexistentes"):
        apply_transforms(_frame(), _steps({"op": "select_columns", "columns": ["nao_existe"]}))


def test_python_hook():
    out = apply_transforms(
        _frame(), _steps({"op": "python", "callable": "test_transforms:double_valor"})
    )
    assert out["valor_dobro"].tolist()[:2] == ["20", "500"]


def test_invalid_filter_config_rejected():
    with pytest.raises(ValidationError):
        _steps({"op": "filter", "column": "uf", "operator": "in", "value": "MT"})
    with pytest.raises(ValidationError):
        _steps({"op": "filter", "column": "uf", "operator": "regex", "value": "("})
