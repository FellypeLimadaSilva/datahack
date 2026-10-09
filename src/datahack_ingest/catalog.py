from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENT = r"^[a-z][a-z0-9_]{0,62}$"
SRC_COLUMN = r"^[A-Za-z_][A-Za-z0-9_\.]*$"
CALLABLE_REF = r"^[A-Za-z_][A-Za-z0-9_\.]*:[A-Za-z_][A-Za-z0-9_]*$"

LoadStrategy = Literal["full", "append", "merge"]
WatermarkType = Literal["timestamp", "integer", "string"]
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


class HashColumns(_Strict):
    op: Literal["hash_columns"]
    columns: list[Ident]
    salt_env: str = "DBT_PII_SALT"
    digits_only: bool = False


class MaskColumns(_Strict):
    op: Literal["mask_columns"]
    columns: list[Ident]
    keep_last: Annotated[int, Field(ge=0)] = 4
    char: Annotated[str, Field(min_length=1, max_length=1)] = "*"


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


class Deduplicate(_Strict):
    op: Literal["deduplicate"]
    keys: list[Ident]
    keep: Literal["first", "last"] = "last"


class AddConstant(_Strict):
    op: Literal["add_constant"]
    column: Ident
    value: str


class TextCase(_Strict):
    op: Literal["trim", "upper", "lower"]
    columns: list[Ident]


class PythonHook(_Strict):
    op: Literal["python"]
    callable: Annotated[str, Field(pattern=CALLABLE_REF)]


TransformStep = Annotated[
    DropColumns
    | SelectColumns
    | RenameColumns
    | HashColumns
    | MaskColumns
    | FilterRows
    | Deduplicate
    | AddConstant
    | TextCase
    | PythonHook,
    Field(discriminator="op"),
]


class DeleteDetection(_Strict):
    mode: Literal["soft", "hard"] = "soft"
    scope: Literal["snapshot", "keys_query"] = "snapshot"
    keys_query: str | None = None
    max_delete_ratio: Annotated[float, Field(gt=0, le=1)] = 0.5


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


FileFormat = Literal["csv", "jsonl", "json", "parquet", "xlsx", "xml", "fixed_width", "avro", "orc"]


DEFAULT_EXCLUDE = [".*", "~$*", "*.tmp", "*.part", "*.crdownload", "_source.yml"]


class FileOptions(_Strict):
    path: str
    format: FileFormat
    compression: Literal["infer", "none", "gzip", "bz2", "xz", "zstd", "zip"] = "infer"
    zip_member_pattern: str = "*"
    include: list[str] = ["*"]
    exclude: list[str] = DEFAULT_EXCLUDE
    min_age_seconds: Annotated[int, Field(ge=0)] = 0
    sep: str = ","
    encoding: str = "auto"
    quotechar: str = '"'
    skip_rows: int = 0
    records_path: str | None = None
    sheet_name: str | int = 0
    flatten_max_level: int = 1
    record_tag: str | None = None
    widths: list[Annotated[int, Field(gt=0)]] | None = None
    names: list[str] | None = None

    @model_validator(mode="after")
    def _format_rules(self) -> FileOptions:
        if self.sep != "auto" and len(self.sep) != 1 and self.sep != r"\t":
            raise ValueError("sep deve ser um caractere ou 'auto'")
        if self.format == "fixed_width":
            if not self.widths:
                raise ValueError("format fixed_width exige widths")
            if self.names and len(self.names) != len(self.widths):
                raise ValueError("fixed_width: names e widths devem ter o mesmo tamanho")
        return self


class ApiAuth(_Strict):
    type: Literal["none", "bearer", "header", "basic", "oauth2_client_credentials"] = "none"
    token_env: str | None = None
    header: str = "X-API-Key"
    username_env: str | None = None
    password_env: str | None = None
    token_url: str | None = None
    client_id_env: str | None = None
    client_secret_env: str | None = None
    scope: str | None = None
    audience: str | None = None
    client_auth: Literal["body", "basic"] = "body"

    @model_validator(mode="after")
    def _oauth_rules(self) -> ApiAuth:
        if self.type == "oauth2_client_credentials" and not (
            self.token_url and self.client_id_env and self.client_secret_env
        ):
            raise ValueError(
                "oauth2_client_credentials exige token_url, client_id_env e client_secret_env"
            )
        return self


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


class GraphQLOptions(_Strict):
    query: str
    variables: dict[str, Any] = {}
    cursor_variable: str = "after"
    page_info_path: str | None = None


class ApiOptions(_Strict):
    url: str
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = {}
    params: dict[str, Any] = {}
    body: dict[str, Any] | None = None
    auth: ApiAuth = ApiAuth()
    pagination: ApiPagination = ApiPagination()
    graphql: GraphQLOptions | None = None
    records_path: str | None = None
    incremental_param: str | None = None
    timeout_seconds: float = 60
    max_retries: int = 5
    verify_tls: bool = True
    rate_limit_per_second: float | None = None
    flatten_max_level: int = 1

    @model_validator(mode="after")
    def _graphql_rules(self) -> ApiOptions:
        if self.graphql and self.pagination.type != "none":
            raise ValueError("graphql usa paginação própria (page_info_path); remova 'pagination'")
        if self.graphql and not self.records_path:
            raise ValueError("graphql exige records_path (ex.: data.pedidos.nodes)")
        return self


class SqlPartition(_Strict):
    column: Annotated[str, Field(pattern=SRC_COLUMN)]
    num_partitions: Annotated[int, Field(ge=2, le=64)] = 4
    lower_bound: int | None = None
    upper_bound: int | None = None


class SqlOptions(_Strict):
    url_env: str | None = None
    url: str | None = None
    query: str | None = None
    table: str | None = None
    partition: SqlPartition | None = None

    @model_validator(mode="after")
    def _one_of(self) -> SqlOptions:
        if bool(self.url_env) == bool(self.url):
            raise ValueError("informe exatamente um entre 'url_env' e 'url'")
        if self.url and not self.url.startswith("sqlite:///"):
            raise ValueError("'url' literal só é aceito para sqlite; use url_env para credenciais")
        if bool(self.query) == bool(self.table):
            raise ValueError("informe exatamente um entre 'query' e 'table'")
        if self.table and not re.match(SRC_COLUMN, self.table):
            raise ValueError(f"nome de tabela inválido: {self.table!r}")
        return self


class _SourceBase(_Strict):
    name: Ident
    description: str = ""
    owner: str | None = None
    enabled: bool = True
    tags: list[str] = []
    sink: Literal["postgres", "parquet"] = "postgres"
    target_table: Ident | None = None
    load_strategy: LoadStrategy = "append"
    primary_key: list[Ident] = []
    watermark_column: Annotated[str | None, Field(pattern=SRC_COLUMN)] = None
    watermark_type: WatermarkType = "timestamp"
    chunk_size: Annotated[int, Field(ge=100, le=1_000_000)] = 50_000
    pii_columns: list[str] = []
    transforms: list[TransformStep] = []
    delete_detection: DeleteDetection | None = None
    volume_check: VolumeCheck | None = None
    auto_model: bool = True

    @property
    def table(self) -> str:
        return self.target_table or self.name

    @model_validator(mode="after")
    def _strategy_rules(self) -> _SourceBase:
        if self.load_strategy == "merge" and not self.primary_key:
            raise ValueError(f"{self.name}: load_strategy=merge exige primary_key")
        if self.sink == "parquet" and self.load_strategy == "merge":
            raise ValueError(f"{self.name}: sink parquet aceita apenas full/append")
        dd = self.delete_detection
        if dd:
            if self.load_strategy != "merge" or self.sink != "postgres":
                raise ValueError(f"{self.name}: delete_detection exige merge no sink postgres")
            if dd.scope == "snapshot" and self.watermark_column:
                raise ValueError(
                    f"{self.name}: delete_detection snapshot exige extração completa; "
                    "com watermark use scope keys_query"
                )
            if dd.scope == "keys_query" and not dd.keys_query:
                raise ValueError(f"{self.name}: scope keys_query exige keys_query")
        return self


class FileSource(_SourceBase):
    kind: Literal["file"]
    file: FileOptions

    @model_validator(mode="after")
    def _file_rules(self) -> FileSource:
        if self.delete_detection and self.delete_detection.scope == "keys_query":
            raise ValueError(f"{self.name}: keys_query só é suportado em fontes sql")
        return self


class ApiSource(_SourceBase):
    kind: Literal["api"]
    api: ApiOptions

    @model_validator(mode="after")
    def _api_rules(self) -> ApiSource:
        if self.delete_detection and self.delete_detection.scope == "keys_query":
            raise ValueError(f"{self.name}: keys_query só é suportado em fontes sql")
        return self


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


def required_env_vars(source: FileSource | ApiSource | SqlSource) -> list[str]:
    names: list[str] = []
    if isinstance(source, SqlSource) and source.sql.url_env:
        names.append(source.sql.url_env)
    if isinstance(source, ApiSource):
        a = source.api.auth
        names += [
            n
            for n in (
                a.token_env,
                a.username_env,
                a.password_env,
                a.client_id_env,
                a.client_secret_env,
            )
            if n
        ]
    names += [t.salt_env for t in source.transforms if isinstance(t, HashColumns)]
    return names
