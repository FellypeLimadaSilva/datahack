from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from datahack_ingest.normalize import (
    normalize_columns,
    normalize_identifier,
    to_text,
    to_text_frame,
)


def test_identifier_accents_spaces_and_camel_case():
    assert normalize_identifier("Data Inauguração") == "data_inauguracao"
    assert normalize_identifier("precoLista") == "preco_lista"
    assert normalize_identifier("Área (m²)") == "area_m2"
    assert normalize_identifier("2024 total") == "c_2024_total"
    assert normalize_identifier("", 4) == "col_5"


def test_identifier_never_collides_with_metadata_prefix():
    assert not normalize_identifier("_dh_batch_id").startswith("_")


def test_identifier_max_length_63():
    assert len(normalize_identifier("x" * 200)) == 63


def test_duplicate_columns_are_disambiguated():
    assert normalize_columns(["Valor", "valor", "VALOR"]) == ["valor", "valor_2", "valor_3"]


def test_to_text_types():
    assert to_text(None) is None
    assert to_text(float("nan")) is None
    assert to_text(pd.NA) is None
    assert to_text("a\x00b") == "ab"
    assert to_text(True) == "true"
    assert to_text(10) == "10"
    assert to_text(1.5) == "1.5"
    assert to_text(Decimal("10.50")) == "10.50"
    assert to_text(date(2026, 1, 2)) == "2026-01-02"
    assert to_text(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02 03:04:05"
    assert to_text({"a": [1, 2]}) == '{"a": [1, 2]}'
    assert to_text(b"\x01\xff") == "01ff"


def test_frame_keeps_none_as_none_not_nan_string():
    df = pd.DataFrame({"a": ["x", None, "y"], "b": [1, None, 3]}, dtype=object)
    out = to_text_frame(df)
    assert out["a"].tolist() == ["x", None, "y"]
    assert out["b"].tolist() == ["1", None, "3"]
    assert all(dt is np.dtype(object) for dt in out.dtypes)


def test_frame_string_dtype_fast_path_removes_nul():
    df = pd.DataFrame({"Col A": pd.Series(["a\x00", None], dtype="string")})
    out = to_text_frame(df)
    assert list(out.columns) == ["col_a"]
    assert out["col_a"].tolist() == ["a", None]


def test_integers_with_nulls_are_not_turned_into_floats():
    df = pd.DataFrame({"id": np.array([1, None], dtype=object)})
    assert to_text_frame(df)["id"].tolist() == ["1", None]
