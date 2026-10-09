from __future__ import annotations

import logging
import os
import re
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg import sql
from psycopg.rows import dict_row

from datahack_ingest.catalog import Catalog
from datahack_ingest.normalize import MAX_IDENT, normalize_identifier
from datahack_ingest.settings import Settings

log = logging.getLogger(__name__)

AUTO_DIR = "auto"
SOURCE_NAME = "bronze_auto"
SILVER_PREFIX = "auto_silver__"
GOLD_PREFIX = "auto_gold__"
META = ("_dh_batch_id", "_dh_ingested_at", "_dh_source_file", "_dh_row_hash", "_dh_deleted_at")
PROFILE_BATCH = 40
MAX_KEY_CANDIDATES = 6

KEY_EXACT = ("id", "codigo", "cod", "uuid", "guid", "chave", "pk", "sk")
KEY_AFFIXES = ("{t}_id", "id_{t}", "cod_{t}", "codigo_{t}", "{t}_codigo", "{t}_cod", "{t}_uuid")
_PLURALS = (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ns", "m"), ("res", "r"))
CODE_NAME = re.compile(
    r"(^|_)(cpf|cnpj|cep|telefone|tel|celular|fone|rg|pis|nis|chave|matricula|codigo|cod|ncm|cfop"
    r"|ean|gtin|isbn|conta|agencia|cartao|protocolo|processo|inscricao)(_|$)"
)
IDENT_PII = re.compile(
    r"(^|_)(cpf|rg|email|e_mail|telefone|tel|celular|fone|phone|whatsapp|cartao|card|pis|nis"
    r"|pasep|cns|titulo_eleitor|passaporte|cnh)(_|$)"
)
DIGIT_PII = re.compile(
    r"(^|_)(cpf|telefone|tel|celular|fone|phone|whatsapp|cartao|card|pis|nis|pasep|cns|cnh)(_|$)"
)
PERSON_ROLES = (
    "cliente|pessoa|usuario|paciente|aluno|titular|contato|responsavel|funcionario"
    "|colaborador|servidor|mae|pai|completo|social"
)
PERSONAL = re.compile(
    rf"^(nome|name)(_({PERSON_ROLES}))?$|^({PERSON_ROLES})_(nome|name)$"
    r"|(^|_)(endereco|logradouro|address|nascimento|dt_nasc|data_nasc|birth|sexo|genero|bairro"
    r"|ip_address|cep)(_|$)"
)
BOOL_VALUES = ("true", "false", "t", "f", "sim", "nao", "não", "s", "n", "yes", "no", "y")

_CLEAN_MONEY = r"regexp_replace({v}, '(R\$|\s)', '', 'g')"
_DMY = r"regexp_replace({v}, '^(\d{{1,2}})[/.-](\d{{1,2}})[/.-](\d{{4}})$', '\3-\2-\1')"
_MDY = r"regexp_replace({v}, '^(\d{{1,2}})[/.-](\d{{1,2}})[/.-](\d{{4}})$', '\3-\1-\2')"
_TS_DMY = (
    r"regexp_replace({v}, '^(\d{{1,2}})[/.-](\d{{1,2}})[/.-](\d{{4}})[ T](.+)$', '\3-\2-\1 \4')"
)

CHECKS: dict[str, str] = {
    "int_ok": r"{v} ~ '^[+-]?\d{{1,18}}$' AND pg_input_is_valid({v}, 'bigint')",
    "lead0": r"{v} ~ '^[+-]?0\d'",
    "digits": r"{v} ~ '^\d+$'",
    "num_ok": (
        r"{m} ~ '^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$' AND pg_input_is_valid({m}, 'numeric')"
    ),
    "br_ok": r"{m} ~ '^[+-]?(\d{{1,3}}(\.\d{{3}})+|\d+)(,\d+)?$'",
    "br_comma": r"{m} ~ ',\d+$'",
    "date_iso": r"{v} ~ '^\d{{4}}-\d{{2}}-\d{{2}}$' AND pg_input_is_valid({v}, 'date')",
    "date_dmy": (
        r"{v} ~ '^\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{4}}$' AND pg_input_is_valid(" + _DMY + ", 'date')"
    ),
    "date_mdy": (
        r"{v} ~ '^\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{4}}$' AND pg_input_is_valid(" + _MDY + ", 'date')"
    ),
    "ts_iso": (
        r"{v} ~ '^\d{{4}}-\d{{2}}-\d{{2}}[ T]\d{{1,2}}:\d{{2}}'"
        r" AND pg_input_is_valid({v}, 'timestamptz')"
    ),
    "ts_tz": r"{v} ~ '^\d{{4}}-\d{{2}}-\d{{2}}[ T].*(Z|[+-]\d{{2}}(:?\d{{2}})?)$'",
    "ts_dmy": (
        r"{v} ~ '^\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{4}}[ T]\d{{1,2}}:\d{{2}}(:\d{{2}}(\.\d+)?)?$'"
        r" AND pg_input_is_valid(" + _TS_DMY + ", 'timestamp')"
    ),
    "bool_ok": "lower({v}) IN (" + ", ".join(f"'{b}'" for b in BOOL_VALUES) + ")",
    "email": r"{v} ~* '^[^@\s]+@[^@\s]+\.[a-z]{{2,}}$'",
    "cpf_fmt": r"{v} ~ '^\d{{3}}\.\d{{3}}\.\d{{3}}-\d{{2}}$'",
    "phone": (r"{v} ~ '^(\+?55\s?)?\(?\d{{2}}\)?\s?9?\d{{4}}[-\s]?\d{{4}}$' AND {v} ~ '[()+\s-]'"),
    "eleven": r"regexp_replace({v}, '\D', '', 'g') ~ '^\d{{11}}$'",
    "midnight": r"{v} ~ '^\d{{4}}-\d{{2}}-\d{{2}}[ T]00:00(:00(\.0+)?)?$'",
    "json_ok": r"{v} ~ '^\s*[\[{{]' AND pg_input_is_valid({v}, 'jsonb')",
}


@dataclass
class ColumnStats:
    rows: int
    nn: int
    nd: int
    maxlen: int
    counts: dict[str, int]

    def ratio(self, key: str) -> float:
        return self.counts.get(key, 0) / self.nn if self.nn else 0.0


@dataclass
class ColumnSpec:
    name: str
    ordinal: int
    inferred_type: str = "text"
    type_format: str | None = None
    pii_class: str | None = None
    hash_digits: bool = False
    is_key: bool = False
    valid_ratio: float | None = None
    null_ratio: float | None = None
    distinct_ratio: float | None = None
    max_length: int | None = None
    sample_rows: int | None = None
    output_name: str = ""

    @property
    def hashed(self) -> bool:
        return self.pii_class == "identificador"


@dataclass
class TableSpec:
    table: str
    source: str
    columns: list[ColumnSpec]
    key_columns: list[str] = field(default_factory=list)
    dedup: str = "row_hash"
    materialization: str = "table"
    row_count: int = 0
    silver_alias: str = ""
    gold_alias: str = ""

    @property
    def silver_model(self) -> str:
        return f"{SILVER_PREFIX}{self.table}"

    @property
    def gold_model(self) -> str:
        return f"{GOLD_PREFIX}{self.table}"


def cpf_is_valid(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(d) * w for d, w in zip(digits[:size], range(size + 1, 1, -1), strict=True))
        check = (total * 10) % 11 % 10
        if check != int(digits[size]):
            return False
    return True


TYPE_RULES: tuple[tuple[str, str, str | None], ...] = (
    ("int_ok", "bigint", None),
    ("date_iso", "date", "iso"),
    ("date_dmy", "date", "dmy"),
    ("date_mdy", "date", "mdy"),
    ("ts_iso", "timestamp", "iso"),
    ("ts_dmy", "timestamp", "dmy"),
    ("br_ok", "numeric", ","),
    ("num_ok", "numeric", "."),
)


def _is_code(name: str, st: ColumnStats, threshold: float) -> bool:
    return st.ratio("digits") >= threshold and (
        st.counts.get("lead0", 0) > 0 or st.maxlen >= 15 or bool(CODE_NAME.search(name))
    )


def decide_type(name: str, st: ColumnStats, threshold: float) -> tuple[str, str | None, float]:
    if st.nn == 0 or _is_code(name, st, threshold):
        return "text", None, 1.0
    if st.ratio("bool_ok") >= threshold and st.nd <= 3:
        return "boolean", None, st.ratio("bool_ok")
    if st.ratio("json_ok") >= threshold:
        return "jsonb", None, st.ratio("json_ok")
    if st.ratio("ts_iso") >= threshold and st.counts.get("midnight", 0) == st.nn:
        return "date", "iso", st.ratio("ts_iso")
    for check, kind, fmt in TYPE_RULES:
        ratio = st.ratio(check)
        if ratio < threshold:
            continue
        if check == "br_ok" and not st.counts.get("br_comma", 0):
            continue
        with_tz = check == "ts_iso" and st.counts.get("ts_tz", 0) > 0
        return ("timestamptz" if with_tz else kind), fmt, ratio
    return "text", None, 1.0


def classify_pii(
    name: str, st: ColumnStats | None, cpf_ratio: float | None, declared: bool
) -> tuple[str | None, bool]:
    digits = bool(DIGIT_PII.search(name))
    if declared or IDENT_PII.search(name):
        return "identificador", digits or bool(cpf_ratio and cpf_ratio >= 0.9)
    if st and st.nn:
        if st.ratio("email") >= 0.9:
            return "identificador", False
        if st.ratio("cpf_fmt") >= 0.9 or (cpf_ratio is not None and cpf_ratio >= 0.9):
            return "identificador", True
        if st.ratio("phone") >= 0.9:
            return "identificador", True
    if PERSONAL.search(name):
        return "pessoal", False
    return None, False


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def cast_macro(col: ColumnSpec) -> str:
    ref = f"'{_q(col.name)}'"
    fmt = col.type_format
    if col.hashed:
        call = f"dh_hash_pii({ref}, digits_only={'true' if col.hash_digits else 'false'})"
    else:
        call = {
            "bigint": f"dh_to_int({ref})",
            "numeric": f"dh_to_numeric({ref}, decimal='{fmt or '.'}')",
            "date": f"dh_to_date({ref}, '{fmt or 'iso'}')",
            "timestamp": f"dh_to_timestamp({ref}, '{fmt or 'iso'}', tz=false)",
            "timestamptz": f"dh_to_timestamp({ref}, '{fmt or 'iso'}', tz=true)",
            "boolean": f"dh_to_bool({ref})",
            "jsonb": f"dh_to_jsonb({ref})",
        }.get(col.inferred_type, f"dh_clean_text({ref})")
    return f"{{{{ {call} }}}}"


def _invalid_expression(columns: list[ColumnSpec]) -> str:
    typed = [c for c in columns if not c.hashed and c.inferred_type != "text"]
    if not typed:
        return "0"
    parts = [
        f"(case when {{{{ dh_clean_text('{_q(c.name)}') }}}} is not null "
        f"and {cast_macro(c)} is null then 1 else 0 end)"
        for c in typed
    ]
    return "\n        + ".join(parts)


def render_silver(spec: TableSpec, lookback_var: str = "incremental_lookback") -> str:
    if spec.dedup == "key":
        keys = [f"nullif(btrim({_q(k)}), '')" for k in spec.key_columns]
        filters = [f"{k} is not null" for k in keys]
    else:
        keys, filters = ["_dh_row_hash"], []
    out_keys = (
        [_q(c.output_name) for c in spec.columns if c.name in spec.key_columns]
        if spec.dedup == "key"
        else ["_dh_row_hash"]
    )
    if spec.materialization == "incremental":
        unique = ", ".join(repr(k) for k in out_keys)
        config = (
            f"{{{{ config(\n    materialized='incremental',\n    alias='{spec.silver_alias}',\n"
            f"    unique_key=[{unique}],\n    incremental_strategy='merge',\n"
            f"    on_schema_change='append_new_columns'\n) }}}}"
        )
        incremental = (
            "\n    {% if is_incremental() %}\n"
            f"    {'and' if filters else 'where'} _dh_ingested_at >= (\n"
            "        select coalesce(max(_dh_ingested_at), '-infinity'::timestamptz) "
            "from {{ this }}\n"
            f"    ) - interval '{{{{ var(\"{lookback_var}\") }}}}'\n"
            "    {% endif %}"
        )
    else:
        config = f"{{{{ config(materialized='table', alias='{spec.silver_alias}') }}}}"
        incremental = ""
    where = ("\n    where " + "\n      and ".join(filters)) if filters else ""
    select_cols = ",\n    ".join(f"{cast_macro(c)} as {_q(c.output_name)}" for c in spec.columns)
    return (
        f"{config}\n\n"
        "with base as (\n"
        "    select *\n"
        f"    from {{{{ source('{SOURCE_NAME}', '{spec.table}') }}}}{where}{incremental}\n"
        "),\n\n"
        "ranked as (\n"
        "    select\n"
        "        base.*,\n"
        "        row_number() over (\n"
        f"            partition by {', '.join(keys)}\n"
        "            order by _dh_ingested_at desc, _dh_source_file desc\n"
        "        ) as _dh_rn\n"
        "    from base\n"
        ")\n\n"
        "select\n"
        f"    {select_cols},\n"
        f"    (\n        {_invalid_expression(spec.columns)}\n    ) as _dh_invalid_columns,\n"
        "    _dh_row_hash,\n"
        "    _dh_source_file,\n"
        "    _dh_batch_id,\n"
        "    _dh_ingested_at,\n"
        "    _dh_deleted_at\n"
        "from ranked\n"
        "where _dh_rn = 1\n"
    )


def render_gold(spec: TableSpec) -> str:
    cols = ",\n    ".join(_q(c.output_name) for c in spec.columns)
    return (
        f"{{{{ config(materialized='view', alias='{spec.gold_alias}') }}}}\n\n"
        "select\n"
        f"    {cols},\n"
        "    _dh_ingested_at as dh_atualizado_em\n"
        f"from {{{{ ref('{spec.silver_model}') }}}}\n"
        "where _dh_deleted_at is null\n"
    )


def _column_doc(c: ColumnSpec) -> str:
    parts = [f"Tipo inferido: {c.inferred_type}"]
    if c.type_format and c.inferred_type != "text":
        parts.append(f"formato {c.type_format}")
    if c.hashed:
        parts.append("PII pseudonimizada (SHA-256 com salt)")
    elif c.pii_class == "pessoal":
        parts.append("possível dado pessoal (LGPD)")
    if c.is_key:
        parts.append("chave")
    parts.append(f"origem bronze.{c.name}")
    return "; ".join(parts) + "."


def _source_table(s: TableSpec) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": s.table,
        "description": f"Fonte {s.source} (geração automática).",
    }
    if s.dedup == "key":
        entry["columns"] = [
            {
                "name": k,
                "quote": True,
                "description": "Chave detectada; linhas com chave nula não chegam à Silver.",
                "data_tests": [{"not_null": {"config": {"severity": "warn"}}}],
            }
            for k in s.key_columns
        ]
    return entry


def render_yaml(specs: list[TableSpec]) -> tuple[str, str]:
    sources = {
        "version": 2,
        "sources": [
            {
                "name": SOURCE_NAME,
                "schema": "bronze",
                "description": "Tabelas Bronze com Silver e Gold geradas automaticamente.",
                "loaded_at_field": "_dh_ingested_at",
                "tables": [_source_table(s) for s in specs],
            }
        ],
    }
    models: list[dict[str, Any]] = []
    for s in specs:
        key_cols = [c for c in s.columns if c.is_key]
        silver_tests: list[Any] = []
        columns: list[dict[str, Any]] = []
        for c in s.columns:
            entry: dict[str, Any] = {
                "name": c.output_name,
                "quote": True,
                "description": _column_doc(c),
            }
            if c.is_key and len(key_cols) == 1:
                entry["data_tests"] = ["not_null", "unique"]
            elif c.is_key:
                entry["data_tests"] = ["not_null"]
            columns.append(entry)
        if s.dedup == "row_hash":
            columns.append({"name": "_dh_row_hash", "data_tests": ["not_null", "unique"]})
        elif len(key_cols) > 1:
            silver_tests.append(
                {
                    "dh_unique_combination": {
                        "arguments": {
                            "combination_of_columns": [_q(c.output_name) for c in key_cols]
                        }
                    }
                }
            )
        columns.append(
            {
                "name": "_dh_invalid_columns",
                "description": "Quantidade de colunas cujo valor não coube no tipo inferido.",
                "data_tests": [
                    {
                        "dh_invalid_ratio": {
                            "arguments": {"max_ratio": 0.0},
                            "config": {"severity": "warn"},
                        }
                    }
                ],
            }
        )
        silver: dict[str, Any] = {
            "name": s.silver_model,
            "description": (
                f"Silver automática de bronze.{s.table}: tipada, deduplicada "
                f"({'chave ' + ', '.join(s.key_columns) if s.dedup == 'key' else 'hash da linha'})"
                " e com PII pseudonimizada."
            ),
            "config": {"tags": ["auto", "silver"]},
            "columns": columns,
        }
        if silver_tests:
            silver["data_tests"] = silver_tests
        models.append(silver)
        models.append(
            {
                "name": s.gold_model,
                "description": f"Gold automática de bronze.{s.table}, pronta para consumo no BI.",
                "config": {"tags": ["auto", "gold"]},
            }
        )
    dump = {"width": 100, "sort_keys": False, "allow_unicode": True}
    return yaml.safe_dump(sources, **dump), yaml.safe_dump({"version": 2, "models": models}, **dump)


def handwritten_tables(models_dir: Path) -> tuple[set[str], set[str]]:
    pattern = re.compile(r"source\(\s*['\"]bronze['\"]\s*,\s*['\"]([A-Za-z0-9_]+)['\"]\s*\)")
    tables: set[str] = set()
    names: set[str] = set()
    auto = models_dir / AUTO_DIR
    for path in models_dir.rglob("*.sql"):
        if auto in path.parents:
            continue
        names.add(path.stem)
        tables.update(pattern.findall(path.read_text(encoding="utf-8")))
    return tables, names


class ModelGenerator:
    def __init__(
        self, settings: Settings, catalog: Catalog, reset: bool = False, prune: bool = True
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.reset = reset
        self.prune = prune
        self.models_dir = settings.dbt_project_dir / "models"
        self.threshold = settings.auto_type_threshold
        self.skipped: list[dict[str, str]] = []

    def run(self, conn: psycopg.Connection, write: bool = True) -> list[TableSpec]:
        lock = zlib.crc32(b"dh_generate_models")
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (lock,)).fetchone()[0]:
            raise RuntimeError("generate-models já está em execução")
        try:
            specs = self._build(conn)
            if write:
                self._persist(conn, specs)
                self._write_files(specs)
            return specs
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (lock,))

    def _targets(self, conn: psycopg.Connection) -> list[tuple[str, Any]]:
        handled, model_names = handwritten_tables(self.models_dir)
        existing = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'bronze'"
            )
        }
        targets = []
        for source in self.catalog.enabled():
            table = source.table
            if source.sink != "postgres" or not source.auto_model:
                continue
            if table in handled:
                self.skipped.append({"table": table, "reason": "modelada manualmente no dbt"})
                continue
            if table not in existing:
                self.skipped.append({"table": table, "reason": "ainda sem dados na Bronze"})
                continue
            targets.append((table, source))
        self._model_names = model_names
        return targets

    def _build(self, conn: psycopg.Connection) -> list[TableSpec]:
        previous_cols, previous_tables = self._previous(conn)
        specs = []
        for table, source in self._targets(conn):
            spec = self._table_spec(
                conn,
                table,
                source,
                {} if self.reset else previous_cols.get(table, {}),
                None if self.reset else previous_tables.get(table),
            )
            if self.reset and table in previous_tables:
                spec.materialization = "table"
            specs.append(spec)
        return specs

    def _previous(self, conn: psycopg.Connection):
        cols: dict[str, dict[str, dict[str, Any]]] = {}
        with conn.cursor(row_factory=dict_row) as cur:
            for row in cur.execute("SELECT * FROM ops.data_catalog"):
                cols.setdefault(row["table_name"], {})[row["column_name"]] = row
            tables = {r["table_name"]: r for r in cur.execute("SELECT * FROM ops.auto_models")}
        return cols, tables

    def _table_spec(self, conn, table, source, prev_cols, prev_table) -> TableSpec:
        names = [
            r[0]
            for r in conn.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema = 'bronze' AND table_name = %s ORDER BY ordinal_position""",
                (table,),
            )
            if r[0] not in META
        ]
        rows = _row_count(conn, table)
        declared_pii = {normalize_identifier(c) for c in source.pii_columns}
        fresh = [n for n in names if n not in prev_cols]
        stats, sample_rows = self._profile(conn, table, fresh, rows) if fresh else ({}, 0)
        cpf = self._cpf_ratios(conn, table, fresh, stats, rows)

        columns: list[ColumnSpec] = []
        for i, name in enumerate(names, start=1):
            prev = prev_cols.get(name)
            if prev:
                col = ColumnSpec(
                    name=name,
                    ordinal=i,
                    inferred_type=prev["inferred_type"],
                    type_format=prev["type_format"],
                    pii_class=prev["pii_class"],
                    hash_digits=prev["hash_digits"],
                    valid_ratio=_f(prev["valid_ratio"]),
                    null_ratio=_f(prev["null_ratio"]),
                    distinct_ratio=_f(prev["distinct_ratio"]),
                    max_length=prev["max_length"],
                    sample_rows=prev["sample_rows"],
                )
                if name in declared_pii:
                    col.pii_class = "identificador"
                    col.inferred_type, col.type_format = "text", None
            else:
                st = stats[name]
                kind, fmt, valid = decide_type(name, st, self.threshold)
                pii, digits = classify_pii(name, st, cpf.get(name), name in declared_pii)
                col = ColumnSpec(
                    name=name,
                    ordinal=i,
                    inferred_type="text" if pii == "identificador" else kind,
                    type_format=None if pii == "identificador" else fmt,
                    pii_class=pii,
                    hash_digits=digits,
                    valid_ratio=round(valid, 4),
                    null_ratio=round(1 - st.nn / st.rows, 4) if st.rows else None,
                    distinct_ratio=round(st.nd / st.nn, 4) if st.nn else None,
                    max_length=st.maxlen,
                    sample_rows=sample_rows,
                )
            columns.append(col)
        _assign_output_names(columns)

        key_columns, dedup = self._keys(conn, table, source, columns, prev_table)
        for c in columns:
            c.is_key = c.name in key_columns
        hard_delete = bool(source.delete_detection and source.delete_detection.mode == "hard")
        materialization = (
            "incremental"
            if rows >= self.settings.auto_incremental_rows and not hard_delete
            else "table"
        )
        if prev_table and prev_table["materialization"] == "incremental" and not hard_delete:
            materialization = "incremental"
        spec = TableSpec(
            table=table,
            source=source.name,
            columns=columns,
            key_columns=key_columns,
            dedup=dedup,
            materialization=materialization,
            row_count=rows,
        )
        spec.silver_alias = self._alias(table)
        spec.gold_alias = self._alias(table)
        return spec

    def _alias(self, table: str) -> str:
        if table in self._model_names:
            return f"auto_{table}"[:MAX_IDENT]
        return table

    def _profile(self, conn, table: str, columns: list[str], rows: int):
        limit = self.settings.auto_sample_rows
        target = sql.Identifier("bronze", table)
        sample = sql.SQL("")
        if rows > limit:
            pct = min(100.0, 100.0 * limit * 1.5 / rows)
            sample = sql.SQL(" TABLESAMPLE BERNOULLI ({})").format(sql.Literal(round(pct, 6)))
        stats: dict[str, ColumnStats] = {}
        sample_rows = 0
        for start in range(0, len(columns), PROFILE_BATCH):
            batch = columns[start : start + PROFILE_BATCH]
            cleaned = sql.SQL(", ").join(
                sql.SQL("nullif(btrim({c}), '') AS {a}").format(
                    c=sql.Identifier(c), a=sql.Identifier(f"v{i}")
                )
                for i, c in enumerate(batch)
            )
            aggregates = [sql.SQL("count(*)")]
            for i in range(len(batch)):
                v = f'"v{i}"'
                m = _CLEAN_MONEY.format(v=v)
                aggregates += [
                    sql.SQL(f"count({v})"),
                    sql.SQL(f"count(DISTINCT {v})"),
                    sql.SQL(f"coalesce(max(length({v})), 0)"),
                ]
                aggregates += [
                    sql.SQL(f"count(*) FILTER (WHERE {CHECKS[k].format(v=v, m=m)})") for k in CHECKS
                ]
            query = sql.SQL("SELECT {aggs} FROM (SELECT {cleaned} FROM {t}{s} LIMIT {n}) x").format(
                aggs=sql.SQL(", ").join(aggregates),
                cleaned=cleaned,
                t=target,
                s=sample,
                n=sql.Literal(limit),
            )
            values = conn.execute(query).fetchone()
            sample_rows = values[0]
            width = 3 + len(CHECKS)
            for i, name in enumerate(batch):
                chunk = values[1 + i * width : 1 + (i + 1) * width]
                stats[name] = ColumnStats(
                    rows=sample_rows,
                    nn=chunk[0],
                    nd=chunk[1],
                    maxlen=chunk[2],
                    counts=dict(zip(CHECKS, chunk[3:], strict=True)),
                )
        return stats, sample_rows

    def _cpf_ratios(self, conn, table, columns, stats, rows) -> dict[str, float]:
        out: dict[str, float] = {}
        for name in columns:
            st = stats.get(name)
            if not st or not st.nn or st.ratio("eleven") < 0.9:
                continue
            values = [
                r[0]
                for r in conn.execute(
                    sql.SQL(
                        "SELECT DISTINCT v FROM (SELECT nullif(btrim({c}), '') AS v FROM {t} "
                        "WHERE nullif(btrim({c}), '') IS NOT NULL LIMIT 20000) s LIMIT 500"
                    ).format(c=sql.Identifier(name), t=sql.Identifier("bronze", table))
                )
            ]
            if values:
                out[name] = sum(cpf_is_valid(v) for v in values) / len(values)
        return out

    def _keys(self, conn, table, source, columns, prev_table) -> tuple[list[str], str]:
        names = {c.name for c in columns}
        if source.primary_key:
            declared = [normalize_identifier(k) for k in source.primary_key]
            if all(k in names for k in declared):
                return declared, "key"
        if prev_table is not None:
            previous = [k for k in prev_table["key_columns"] if k in names]
            if prev_table["dedup"] == "key" and previous:
                return previous, "key"
            return [], "row_hash"
        candidates = key_candidates(table, [c.name for c in columns])
        by_name = {c.name: c for c in columns}
        for name in candidates[:MAX_KEY_CANDIDATES]:
            col = by_name[name]
            if col.inferred_type not in ("bigint", "text"):
                continue
            if self._unique_per_file(conn, table, col.name):
                return [col.name], "key"
        return [], "row_hash"

    @staticmethod
    def _unique_per_file(conn, table: str, column: str) -> bool:
        query = sql.SQL(
            """SELECT coalesce(bool_and(n = nn AND nn = nd), false)
               FROM (
                   SELECT count(*) AS n,
                          count(nullif(btrim({c}), '')) AS nn,
                          count(DISTINCT nullif(btrim({c}), '')) AS nd
                   FROM {t} GROUP BY _dh_source_file
               ) x"""
        ).format(c=sql.Identifier(column), t=sql.Identifier("bronze", table))
        return bool(conn.execute(query).fetchone()[0])

    def _persist(self, conn: psycopg.Connection, specs: list[TableSpec]) -> None:
        with conn.transaction():
            current = [s.table for s in specs]
            if self.prune:
                conn.execute(
                    "DELETE FROM ops.auto_models WHERE NOT (table_name = ANY(%s))", (current,)
                )
                conn.execute(
                    "DELETE FROM ops.data_catalog WHERE NOT (table_name = ANY(%s))", (current,)
                )
            for s in specs:
                conn.execute(
                    """INSERT INTO ops.auto_models AS t (table_name, source, model_silver,
                           model_gold, silver_alias, gold_alias, key_columns, dedup,
                           materialization, row_count)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (table_name) DO UPDATE SET
                           source = EXCLUDED.source, model_silver = EXCLUDED.model_silver,
                           model_gold = EXCLUDED.model_gold, silver_alias = EXCLUDED.silver_alias,
                           gold_alias = EXCLUDED.gold_alias, key_columns = EXCLUDED.key_columns,
                           dedup = EXCLUDED.dedup, materialization = EXCLUDED.materialization,
                           row_count = EXCLUDED.row_count, generated_at = now()""",
                    (
                        s.table,
                        s.source,
                        s.silver_model,
                        s.gold_model,
                        s.silver_alias,
                        s.gold_alias,
                        s.key_columns,
                        s.dedup,
                        s.materialization,
                        s.row_count,
                    ),
                )
                names = [c.name for c in s.columns]
                conn.execute(
                    "DELETE FROM ops.data_catalog WHERE table_name = %s "
                    "AND NOT (column_name = ANY(%s))",
                    (s.table, names),
                )
                for c in s.columns:
                    conn.execute(
                        """INSERT INTO ops.data_catalog AS t (table_name, column_name, ordinal,
                               output_name, inferred_type, type_format, pii_class, hash_digits,
                               is_key, valid_ratio, null_ratio, distinct_ratio, max_length,
                               sample_rows)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (table_name, column_name) DO UPDATE SET
                               ordinal = EXCLUDED.ordinal, output_name = EXCLUDED.output_name,
                               inferred_type = EXCLUDED.inferred_type,
                               type_format = EXCLUDED.type_format,
                               pii_class = EXCLUDED.pii_class,
                               hash_digits = EXCLUDED.hash_digits, is_key = EXCLUDED.is_key,
                               valid_ratio = EXCLUDED.valid_ratio,
                               null_ratio = EXCLUDED.null_ratio,
                               distinct_ratio = EXCLUDED.distinct_ratio,
                               max_length = EXCLUDED.max_length,
                               sample_rows = EXCLUDED.sample_rows,
                               profiled_at = CASE
                                   WHEN t.inferred_type IS DISTINCT FROM EXCLUDED.inferred_type
                                     OR t.pii_class IS DISTINCT FROM EXCLUDED.pii_class
                                   THEN now() ELSE t.profiled_at END""",
                        (
                            s.table,
                            c.name,
                            c.ordinal,
                            c.output_name,
                            c.inferred_type,
                            c.type_format,
                            c.pii_class,
                            c.hash_digits,
                            c.is_key,
                            c.valid_ratio,
                            c.null_ratio,
                            c.distinct_ratio,
                            c.max_length,
                            c.sample_rows,
                        ),
                    )

    def _write_files(self, specs: list[TableSpec]) -> None:
        root = self.models_dir / AUTO_DIR
        files: dict[Path, str] = {}
        if specs:
            sources_yml, models_yml = render_yaml(specs)
            files[root / "_auto__sources.yml"] = sources_yml
            files[root / "_auto__models.yml"] = models_yml
            for s in specs:
                files[root / "silver" / f"{s.silver_model}.sql"] = render_silver(s)
                files[root / "gold" / f"{s.gold_model}.sql"] = render_gold(s)
        for path, content in files.items():
            _atomic_write(path, content)
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file() and path not in files:
                    path.unlink()


def singular(word: str) -> str:
    for suffix, replacement in _PLURALS:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + replacement
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def key_candidates(table: str, columns: list[str]) -> list[str]:
    tokens = [t for t in table.split("_") if t]
    stems = {table, singular(table), *tokens, *(singular(t) for t in tokens)}
    affixed = {pattern.format(t=stem) for stem in stems for pattern in KEY_AFFIXES}
    ordered = [c for c in columns if c in KEY_EXACT]
    ordered += [c for c in columns if c in affixed and c not in ordered]
    return ordered


EXACT_COUNT_LIMIT = 5_000_000


def _row_count(conn: psycopg.Connection, table: str) -> int:
    estimate = conn.execute(
        "SELECT c.reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'bronze' AND c.relname = %s",
        (table,),
    ).fetchone()
    if estimate and estimate[0] >= EXACT_COUNT_LIMIT:
        return int(estimate[0])
    target = sql.Identifier("bronze", table)
    return conn.execute(sql.SQL("SELECT count(*) FROM {}").format(target)).fetchone()[0]


def _assign_output_names(columns: list[ColumnSpec]) -> None:
    used: set[str] = set()
    for c in columns:
        base = f"{c.name[: MAX_IDENT - 5]}_hash" if c.hashed else c.name
        name, n = base, 1
        while name in used or name.startswith("_dh_") or name == "dh_atualizado_em":
            n += 1
            suffix = f"_{n}"
            name = base[: MAX_IDENT - len(suffix)] + suffix
        used.add(name)
        c.output_name = name


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _f(value: Any) -> float | None:
    return None if value is None else float(value)
