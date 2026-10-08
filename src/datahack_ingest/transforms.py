from __future__ import annotations

import hashlib
import importlib
import os
import re
from collections.abc import Callable

import pandas as pd

from datahack_ingest.catalog import (
    AddConstant,
    Deduplicate,
    DropColumns,
    FilterRows,
    HashColumns,
    MaskColumns,
    PythonHook,
    RenameColumns,
    SelectColumns,
    TextCase,
)


class TransformError(ValueError):
    pass


def _require(df: pd.DataFrame, columns: list[str], op: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise TransformError(
            f"{op}: colunas inexistentes {missing}; disponíveis {list(df.columns)}"
        )


def _set(df: pd.DataFrame, column: str, values: list) -> None:
    df[column] = pd.Series(values, index=df.index, dtype=object)


def _sha256(value: str | None, salt: str, digits_only: bool) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = re.sub(r"\D", "", value) if digits_only else value.strip().lower()
    return hashlib.sha256(f"{salt}{normalized}".encode()).hexdigest()


def _mask(value: str | None, keep_last: int, char: str) -> str | None:
    if value is None:
        return None
    keep = value[-keep_last:] if keep_last else ""
    return char * (len(value) - len(keep)) + keep


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


def _load_callable(ref: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    module_name, func_name = ref.split(":")
    func = getattr(importlib.import_module(module_name), func_name)
    if not callable(func):
        raise TransformError(f"python: {ref} não é chamável")
    return func


def apply_step(df: pd.DataFrame, step) -> pd.DataFrame:
    if isinstance(step, DropColumns):
        return df.drop(columns=[c for c in step.columns if c in df.columns])
    if isinstance(step, SelectColumns):
        _require(df, step.columns, "select_columns")
        return df[step.columns]
    if isinstance(step, RenameColumns):
        _require(df, list(step.mapping), "rename")
        return df.rename(columns=step.mapping)
    if isinstance(step, HashColumns):
        _require(df, step.columns, "hash_columns")
        salt = os.environ.get(step.salt_env)
        if not salt:
            raise TransformError(f"hash_columns: variável de ambiente {step.salt_env} ausente")
        out = df.copy()
        for c in step.columns:
            _set(out, c, [_sha256(v, salt, step.digits_only) for v in out[c].tolist()])
        return out
    if isinstance(step, MaskColumns):
        _require(df, step.columns, "mask_columns")
        out = df.copy()
        for c in step.columns:
            _set(out, c, [_mask(v, step.keep_last, step.char) for v in out[c].tolist()])
        return out
    if isinstance(step, FilterRows):
        _require(df, [step.column], "filter")
        return df[_filter_mask(df, step).to_numpy(dtype=bool)]
    if isinstance(step, Deduplicate):
        _require(df, step.keys, "deduplicate")
        return df.drop_duplicates(subset=step.keys, keep=step.keep)
    if isinstance(step, AddConstant):
        out = df.copy()
        _set(out, step.column, [step.value] * len(out))
        return out
    if isinstance(step, TextCase):
        _require(df, step.columns, step.op)
        out = df.copy()
        fn = {"trim": str.strip, "upper": str.upper, "lower": str.lower}[step.op]
        for c in step.columns:
            _set(out, c, [fn(v) if isinstance(v, str) else v for v in out[c].tolist()])
        return out
    if isinstance(step, PythonHook):
        result = _load_callable(step.callable)(df.copy())
        if not isinstance(result, pd.DataFrame):
            raise TransformError(f"python: {step.callable} deve retornar DataFrame")
        return result
    raise TransformError(f"transformação não suportada: {type(step).__name__}")


def apply_transforms(df: pd.DataFrame, steps: list) -> pd.DataFrame:
    for step in steps:
        df = apply_step(df, step)
    return df
