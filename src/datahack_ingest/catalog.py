from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENT = r"^[a-z][a-z0-9_]{0,62}$"

LoadStrategy = Literal["full", "append"]
Ident = Annotated[str, Field(pattern=IDENT)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DropColumns(_Strict):
    op: Literal["drop_columns"]
    columns: list[Ident]


class SelectColumns(_Strict):
    op: Literal["select_columns"]
    columns: list[Ident]


class RenameColumns(_Strict):
    op: Literal["rename"]
    mapping: dict[Ident, Ident]


class FilterRows(_Strict):
    op: Literal["filter"]
    column: Ident
    operator: Literal[
        "eq",
        "ne",
        "in",
        "not_in",
        "gt",
        "gte",
        "lt",
        "lte",
        "is_null",
        "not_null",
        "regex",
        "not_regex",
    ]
    value: Any = None

    @model_validator(mode="after")
    def _value_rules(self) -> FilterRows:
        needs_list = self.operator in {"in", "not_in"}
        no_value = self.operator in {"is_null", "not_null"}
        if needs_list and not isinstance(self.value, list):
            raise ValueError(f"filter {self.operator} exige lista em 'value'")
        if not no_value and not needs_list and self.value is None:
            raise ValueError(f"filter {self.operator} exige 'value'")
        if self.operator in {"regex", "not_regex"}:
            try:
                re.compile(str(self.value))
            except re.error as exc:
                raise ValueError(f"regex inválida: {exc}") from exc
        return self


TransformStep = Annotated[
    DropColumns | SelectColumns | RenameColumns | FilterRows,
    Field(discriminator="op"),
]


class VolumeCheck(_Strict):
    lookback_runs: Annotated[int, Field(ge=1, le=100)] = 7
    min_history: Annotated[int, Field(ge=1, le=100)] = 3
    min_ratio: Annotated[float, Field(ge=0)] = 0.5
    max_ratio: Annotated[float, Field(gt=0)] = 3.0
    action: Literal["warn", "fail"] = "warn"

    @model_validator(mode="after")
    def _bounds(self) -> VolumeCheck:
        if self.min_ratio >= self.max_ratio:
            raise ValueError("volume_check: min_ratio deve ser menor que max_ratio")
        if self.min_history > self.lookback_runs:
            raise ValueError("volume_check: min_history não pode exceder lookback_runs")
        return self


FileFormat = Literal["csv", "xlsx"]


DEFAULT_EXCLUDE = [".*", "~$*", "*.tmp", "*.part", "*.crdownload", "_source.yml", "_sources.yml"]


class FileOptions(_Strict):
    path: str
    format: FileFormat
    compression: Literal["infer", "none", "gzip", "bz2", "xz", "zstd", "zip"] = "infer"
    zip_member_pattern: str = "*"
    zip_members: list[str] = []
    include: list[str] = ["*"]
    exclude: list[str] = DEFAULT_EXCLUDE
    recursive: bool = True
    min_age_seconds: Annotated[int, Field(ge=0)] = 0
    sep: str = ","
    encoding: str = "auto"
    quotechar: str = '"'
    skip_rows: Annotated[int, Field(ge=0)] | Literal["auto"] = 0
    drop_note_rows: bool = False
    sheet_name: str | int = 0

    @model_validator(mode="after")
    def _format_rules(self) -> FileOptions:
        if self.sep != "auto" and len(self.sep) != 1 and self.sep != r"\t":
            raise ValueError("sep deve ser um caractere ou 'auto'")
        return self


class ApiOptions(_Strict):
    url: str
    headers: dict[str, str] = {}
    params: dict[str, Any] = {}
    records_path: str | None = None
    timeout_seconds: float = 60
    max_retries: int = 5
    verify_tls: bool = True
    flatten_max_level: int = 1


class _SourceBase(_Strict):
    name: Ident
    description: str = ""
    owner: str | None = None
    enabled: bool = True
    required: bool = True
    tags: list[str] = []
    target_table: Ident | None = None
    load_strategy: LoadStrategy = "append"
    essential_columns: list[Ident] = []
    chunk_size: Annotated[int, Field(ge=100, le=1_000_000)] = 50_000
    transforms: list[TransformStep] = []
    volume_check: VolumeCheck | None = None

    @property
    def table(self) -> str:
        return self.target_table or self.name


class FileSource(_SourceBase):
    kind: Literal["file"]
    file: FileOptions


class ApiSource(_SourceBase):
    kind: Literal["api"]
    api: ApiOptions


Source = Annotated[FileSource | ApiSource, Field(discriminator="kind")]
AnySource = FileSource | ApiSource


class Catalog(_Strict):
    version: Literal[1] = 1
    sources: list[Source]

    @model_validator(mode="after")
    def _unique(self) -> Catalog:
        seen: set[str] = set()
        for s in self.sources:
            for key in {s.name, f"table:{s.table}"}:
                if key in seen:
                    raise ValueError(f"fonte/tabela duplicada no catálogo: {key}")
                seen.add(key)
        return self

    def get(self, name: str) -> AnySource:
        for s in self.sources:
            if s.name == name:
                return s
        raise KeyError(f"fonte não encontrada no catálogo: {name}")

    def enabled(self) -> list[AnySource]:
        return [s for s in self.sources if s.enabled]


def read_catalog_specs(path: str | Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: o catálogo deve ser um mapeamento com 'sources'")
    if raw.get("version", 1) != 1:
        raise ValueError(f"{path}: versão de catálogo não suportada: {raw.get('version')}")
    sources = raw.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError(f"{path}: 'sources' deve ser uma lista")
    return sources


def load_catalog(path: str | Path) -> Catalog:
    return Catalog.model_validate({"sources": read_catalog_specs(path)})
