from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENT = r"^[a-z][a-z0-9_]{0,62}$"
SRC_COLUMN = r"^[A-Za-z_][A-Za-z0-9_\.]*$"

LoadStrategy = Literal["full", "append", "merge"]
WatermarkType = Literal["timestamp", "integer", "string"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileOptions(_Strict):
    path: str = Field(description="Caminho/glob relativo a DH_LANDING_URI (ou URI absoluta).")
    format: Literal["csv", "jsonl", "json", "parquet", "xlsx"]
    sep: str = ","
    encoding: str = "utf-8"
    quotechar: str = '"'
    skip_rows: int = 0
    records_path: str | None = None
    sheet_name: str | int = 0
    flatten_max_level: int = 1


class ApiAuth(_Strict):
    type: Literal["none", "bearer", "header", "basic"] = "none"
    token_env: str | None = None
    header: str = "X-API-Key"
    username_env: str | None = None
    password_env: str | None = None


class ApiPagination(_Strict):
    type: Literal["none", "page", "offset", "cursor", "link_header"] = "none"
    page_param: str = "page"
    size_param: str = "page_size"
    page_size: int = 100
    start_page: int = 1
    offset_param: str = "offset"
    limit_param: str = "limit"
    cursor_param: str = "cursor"
    next_cursor_path: str | None = None
    max_pages: int = 100_000


class ApiOptions(_Strict):
    url: str
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = {}
    params: dict[str, Any] = {}
    body: dict[str, Any] | None = None
    auth: ApiAuth = ApiAuth()
    pagination: ApiPagination = ApiPagination()
    records_path: str | None = None
    incremental_param: str | None = None
    timeout_seconds: float = 60
    max_retries: int = 5
    verify_tls: bool = True
    rate_limit_per_second: float | None = None
    flatten_max_level: int = 1


class SqlOptions(_Strict):
    url_env: str = Field(description="Variável de ambiente com a URL SQLAlchemy da origem.")
    query: str | None = None
    table: str | None = None

    @model_validator(mode="after")
    def _one_of(self) -> SqlOptions:
        if bool(self.query) == bool(self.table):
            raise ValueError("informe exatamente um entre 'query' e 'table'")
        if self.table and not re.match(SRC_COLUMN, self.table):
            raise ValueError(f"nome de tabela inválido: {self.table!r}")
        return self


class _SourceBase(_Strict):
    name: Annotated[str, Field(pattern=IDENT)]
    description: str = ""
    owner: str | None = None
    enabled: bool = True
    tags: list[str] = []
    sink: Literal["postgres", "parquet"] = "postgres"
    target_table: Annotated[str | None, Field(pattern=IDENT)] = None
    load_strategy: LoadStrategy = "append"
    primary_key: list[Annotated[str, Field(pattern=IDENT)]] = []
    watermark_column: Annotated[str | None, Field(pattern=SRC_COLUMN)] = None
    watermark_type: WatermarkType = "timestamp"
    chunk_size: Annotated[int, Field(ge=100, le=1_000_000)] = 50_000
    pii_columns: list[str] = []

    @property
    def table(self) -> str:
        return self.target_table or self.name

    @model_validator(mode="after")
    def _strategy_rules(self) -> _SourceBase:
        if self.load_strategy == "merge" and not self.primary_key:
            raise ValueError(f"{self.name}: load_strategy=merge exige primary_key")
        if self.sink == "parquet" and self.load_strategy == "merge":
            raise ValueError(f"{self.name}: sink parquet aceita apenas full/append")
        return self


class FileSource(_SourceBase):
    kind: Literal["file"]
    file: FileOptions


class ApiSource(_SourceBase):
    kind: Literal["api"]
    api: ApiOptions


class SqlSource(_SourceBase):
    kind: Literal["sql"]
    sql: SqlOptions


Source = Annotated[FileSource | ApiSource | SqlSource, Field(discriminator="kind")]


class Catalog(_Strict):
    version: Literal[1] = 1
    sources: list[Source]

    @model_validator(mode="after")
    def _unique(self) -> Catalog:
        seen: set[str] = set()
        for s in self.sources:
            for key in {s.name, f"table:{s.table}:{s.sink}"}:
                if key in seen:
                    raise ValueError(f"fonte/tabela duplicada no catálogo: {key}")
                seen.add(key)
        return self

    def get(self, name: str) -> FileSource | ApiSource | SqlSource:
        for s in self.sources:
            if s.name == name:
                return s
        raise KeyError(f"fonte não encontrada no catálogo: {name}")

    def enabled(self) -> list[FileSource | ApiSource | SqlSource]:
        return [s for s in self.sources if s.enabled]


def load_catalog(path: str | Path) -> Catalog:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Catalog.model_validate(raw)


def required_env_vars(source: FileSource | ApiSource | SqlSource) -> list[str]:
    names: list[str] = []
    if isinstance(source, SqlSource):
        names.append(source.sql.url_env)
    if isinstance(source, ApiSource):
        a = source.api.auth
        names += [n for n in (a.token_env, a.username_env, a.password_env) if n]
    return names
