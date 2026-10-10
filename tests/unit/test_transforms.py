import pandas as pd
import pytest
from pydantic import ValidationError

from datahack_ingest.catalog import Catalog
from datahack_ingest.transforms import TransformError, apply_transforms


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


def test_chain_filter_drop_rename_select():
    out = apply_transforms(
        _frame(),
        _steps(
            {"op": "filter", "column": "uf", "operator": "eq", "value": "MT"},
            {"op": "drop_columns", "columns": ["cpf"]},
            {"op": "rename", "mapping": {"uf": "sg_uf"}},
            {"op": "select_columns", "columns": ["id", "sg_uf"]},
        ),
    )
    assert out.to_dict("records") == [{"id": "1", "sg_uf": "MT"}, {"id": "3", "sg_uf": "MT"}]


def test_removed_operations_are_rejected():
    for op in ("hash_columns", "mask_columns", "deduplicate", "python"):
        with pytest.raises(ValidationError):
            _steps({"op": op, "columns": ["id"]})


def test_select_unknown_column_fails_with_context():
    with pytest.raises(TransformError, match="inexistentes"):
        apply_transforms(_frame(), _steps({"op": "select_columns", "columns": ["nao_existe"]}))


def test_invalid_filter_config_rejected():
    with pytest.raises(ValidationError):
        _steps({"op": "filter", "column": "uf", "operator": "in", "value": "MT"})
    with pytest.raises(ValidationError):
        _steps({"op": "filter", "column": "uf", "operator": "regex", "value": "("})
