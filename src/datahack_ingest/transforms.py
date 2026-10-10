from __future__ import annotations

import pandas as pd

from datahack_ingest.catalog import DropColumns, FilterRows, RenameColumns, SelectColumns


class TransformError(ValueError):
    pass


def _require(df: pd.DataFrame, columns: list[str], op: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise TransformError(
            f"{op}: colunas inexistentes {missing}; disponíveis {list(df.columns)}"
        )


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _filter_mask(df: pd.DataFrame, step: FilterRows) -> pd.Series:
    s = df[step.column]
    op, value = step.operator, step.value
    if op == "is_null":
        return s.isna()
    if op == "not_null":
        return s.notna()
    if op in {"in", "not_in"}:
        hit = s.isin([str(v) for v in value])
        return hit if op == "in" else ~hit & s.notna()
    if op in {"regex", "not_regex"}:
        hit = s.fillna("").astype(str).str.contains(str(value), regex=True)
        return (hit if op == "regex" else ~hit) & s.notna()
    if op in {"eq", "ne"}:
        hit = s == str(value)
        return hit if op == "eq" else ~hit & s.notna()
    left = _numeric(s)
    right = float(value)
    compare = {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}
    return compare[op].fillna(False)


def apply_step(df: pd.DataFrame, step) -> pd.DataFrame:
    if isinstance(step, DropColumns):
        return df.drop(columns=[c for c in step.columns if c in df.columns])
    if isinstance(step, SelectColumns):
        _require(df, step.columns, "select_columns")
        return df[step.columns]
    if isinstance(step, RenameColumns):
        _require(df, list(step.mapping), "rename")
        return df.rename(columns=step.mapping)
    if isinstance(step, FilterRows):
        _require(df, [step.column], "filter")
        return df[_filter_mask(df, step).to_numpy(dtype=bool)]
    raise TransformError(f"transformação não suportada: {type(step).__name__}")


def apply_transforms(df: pd.DataFrame, steps: list) -> pd.DataFrame:
    for step in steps:
        df = apply_step(df, step)
    return df
