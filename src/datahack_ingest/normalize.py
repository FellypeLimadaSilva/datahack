from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import pandas as pd

MAX_IDENT = 63
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_identifier(name: Any, position: int = 0) -> str:
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text).lower()
    text = _NON_ALNUM.sub("_", text).strip("_")
    if not text:
        text = f"col_{position + 1}"
    if text[0].isdigit():
        text = f"c_{text}"
    return text[:MAX_IDENT]


def normalize_columns(columns: list[Any]) -> list[str]:
    out: list[str] = []
    seen: dict[str, int] = {}
    for i, col in enumerate(columns):
        base = normalize_identifier(col, i)
        name = base
        while name in seen:
            seen[base] += 1
            suffix = f"_{seen[base]}"
            name = base[: MAX_IDENT - len(suffix)] + suffix
        seen.setdefault(name, 1)
        out.append(name)
    return out


def to_text(value: Any) -> str | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return None if math.isnan(value) else repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, ensure_ascii=False, default=str).replace("\x00", "")
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value).replace("\x00", "")


def to_text_frame(df: pd.DataFrame) -> pd.DataFrame:
    data: dict[str, pd.Series] = {}
    for i, name in enumerate(normalize_columns(list(df.columns))):
        series = df.iloc[:, i]
        if pd.api.types.is_object_dtype(series.dtype) or not pd.api.types.is_string_dtype(
            series.dtype
        ):
            values = [to_text(v) for v in series.tolist()]
        else:
            cleaned = series.str.replace("\x00", "", regex=False)
            values = cleaned.to_numpy(dtype=object, na_value=None)
        data[name] = pd.Series(values, index=df.index, dtype=object)
    return pd.DataFrame(data, index=df.index, dtype=object)


def row_hash(df: pd.DataFrame) -> pd.Series:
    hashed = pd.util.hash_pandas_object(df.fillna("\x1f<null>"), index=False)
    return hashed.map(lambda v: f"{int(v):016x}")
