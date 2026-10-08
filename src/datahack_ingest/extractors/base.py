from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from datahack_ingest.normalize import to_text


@dataclass
class ExtractState:
    watermark: Any = None
    loaded_file_hashes: set[str] = field(default_factory=set)
    strategy: str = "append"


@dataclass
class ExtractUnit:
    key: str
    frames: Iterator[pd.DataFrame]
    file_sha256: str | None = None
    file_size: int | None = None


def get_path(obj: Any, path: str | None) -> Any:
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit():
            obj = obj[int(part)]
        else:
            return None
    return obj


def flatten_record(record: Any, max_level: int = 1, sep: str = "_") -> dict[str, str | None]:
    if not isinstance(record, dict):
        return {"value": to_text(record)}
    out: dict[str, str | None] = {}

    def walk(obj: dict, prefix: str, level: int) -> None:
        for key, value in obj.items():
            name = f"{prefix}{sep}{key}" if prefix else str(key)
            if isinstance(value, dict) and level < max_level:
                walk(value, name, level + 1)
            else:
                out[name] = to_text(value)

    walk(record, "", 0)
    return out


def records_to_frame(records: list[Any], max_level: int) -> pd.DataFrame:
    rows = [flatten_record(r, max_level) for r in records]
    return pd.DataFrame(rows, dtype=object)
