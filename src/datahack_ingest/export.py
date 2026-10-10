from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, model_validator

from datahack_ingest import __version__
from datahack_ingest.catalog import IDENT

log = logging.getLogger(__name__)

BASE_CANDIDATES = (
    "qt_ingressante",
    "qt_ing",
    "qt_matricula",
    "qt_mat",
    "qt_aluno",
    "qt_alunos",
    "qt_inscrito_total",
    "qt_concluinte",
    "n_alunos",
    "total_alunos",
    "alunos",
)
MANIFEST = "_manifest.json"
BATCH = 50_000
Format = Literal["csv", "parquet"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExportDefaults(_Strict):
    schema_name: Annotated[str, Field(pattern=IDENT, alias="schema")] = "gold"
    min_cell: Annotated[int, Field(ge=1)] = 10
    formats: list[Format] = ["csv", "parquet"]
    max_file_mb: Annotated[float, Field(gt=0, le=95)] = 50


class ExportTable(_Strict):
    name: Annotated[str, Field(pattern=IDENT)]
    schema_name: Annotated[str | None, Field(pattern=IDENT, alias="schema")] = None
    file_name: Annotated[str | None, Field(pattern=IDENT)] = None
    min_cell_column: list[Annotated[str, Field(pattern=IDENT)]] | None = None
    min_cell: Annotated[int | None, Field(ge=1)] = None
    suppress: bool = True
    where: str | None = None
    order_by: list[Annotated[str, Field(pattern=IDENT)]] | None = None

    @model_validator(mode="before")
    @classmethod
    def _single_column(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("min_cell_column"), str):
            data = {**data, "min_cell_column": [data["min_cell_column"]]}
        return data


class ExportConfig(_Strict):
    version: Literal[1] = 1
    defaults: ExportDefaults = ExportDefaults()
    tables: list[ExportTable] = []

    @model_validator(mode="after")
    def _unique(self) -> ExportConfig:
        names = [t.file_name or t.name for t in self.tables]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise ValueError(f"tabelas de exportação duplicadas: {dup}")
        return self


class ExportError(RuntimeError):
    pass


@dataclass
class TableResult:
    table: str
    rows: int = 0
    suppressed_rows: int = 0
    base_columns: list[str] = field(default_factory=list)
    min_cell: int | None = None
    columns: list[dict[str, str]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)


def load_export_config(path: Path) -> ExportConfig:
    if not path.exists():
        return ExportConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ExportConfig.model_validate(raw)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _columns(conn: psycopg.Connection, schema: str, table: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        """SELECT a.attname, format_type(a.atttypid, a.atttypmod)
           FROM pg_attribute a
           JOIN pg_class c ON c.oid = a.attrelid
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
           ORDER BY a.attnum""",
        (schema, table),
    ).fetchall()
    if not rows:
        raise ExportError(f"{schema}.{table} não existe ou o usuário não tem acesso")
    return [(r[0], r[1]) for r in rows]


def _base_columns(spec: ExportTable, names: list[str]) -> list[str]:
    if not spec.suppress:
        return []
    if spec.min_cell_column:
        missing = [c for c in spec.min_cell_column if c not in names]
        if missing:
            raise ExportError(f"{spec.name}: min_cell_column inexistente: {missing}")
        return list(spec.min_cell_column)
    found = [c for c in BASE_CANDIDATES if c in names]
    if not found:
        raise ExportError(
            f"{spec.name}: nenhuma coluna de contagem de alunos reconhecida; "
            "defina min_cell_column ou suppress: false no exports.yml"
        )
    return found[:1]


ARROW_TYPES: tuple[tuple[tuple[str, ...], pa.DataType], ...] = (
    (("bigint", "integer", "smallint"), pa.int64()),
    (("numeric", "double", "real"), pa.float64()),
    (("boolean",), pa.bool_()),
    (("date",), pa.date32()),
    (("timestamp with time zone",), pa.timestamp("us", tz="UTC")),
    (("timestamp",), pa.timestamp("us")),
)


def _arrow_type(pg_type: str) -> pa.DataType:
    t = pg_type.lower()
    for prefixes, kind in ARROW_TYPES:
        if t.startswith(prefixes):
            return kind
    return pa.string()


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return value


def _arrow_value(value: Any, kind: pa.DataType) -> Any:
    if value is None:
        return None
    if pa.types.is_string(kind) and not isinstance(value, str):
        return (
            json.dumps(value, ensure_ascii=False) if isinstance(value, dict | list) else str(value)
        )
    if pa.types.is_floating(kind):
        return float(value)
    return value


class Exporter:
    def __init__(self, conninfo: str, out_dir: Path, config: ExportConfig) -> None:
        self.conninfo = conninfo
        self.out_dir = out_dir
        self.config = config

    def run(self, only: list[str] | None = None) -> dict[str, Any]:
        tables = [t for t in self.config.tables if not only or t.name in only]
        unknown = sorted(set(only or []) - {t.name for t in tables})
        tables += [ExportTable(name=n) for n in unknown]
        if not tables:
            raise ExportError(
                "nenhuma tabela para exportar: liste em config/exports.yml ou --tables"
            )
        self.out_dir.mkdir(parents=True, exist_ok=True)
        previous = self._previous_files()
        results = []
        with psycopg.connect(self.conninfo, autocommit=False) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            for spec in tables:
                schema = spec.schema_name or self.config.defaults.schema_name
                _base_columns(spec, [c for c, _ in _columns(conn, schema, spec.name)])
            for spec in tables:
                results.append(self._export(conn, spec))
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "platform_version": __version__,
            "min_cell_rule": "linhas com coluna de base abaixo de min_cell ou nula são removidas",
            "tables": [asdict(r) for r in results],
        }
        current = {f["file"] for r in results for f in r.files}
        for stale in previous - current:
            (self.out_dir / stale).unlink(missing_ok=True)
        _atomic_text(self.out_dir / MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        return manifest

    def _previous_files(self) -> set[str]:
        path = self.out_dir / MANIFEST
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {f["file"] for t in data.get("tables", []) for f in t.get("files", [])}
        except (ValueError, KeyError, TypeError):
            return set()

    def _export(self, conn: psycopg.Connection, spec: ExportTable) -> TableResult:
        defaults = self.config.defaults
        schema = spec.schema_name or defaults.schema_name
        min_cell = spec.min_cell or defaults.min_cell
        cols = _columns(conn, schema, spec.name)
        names = [c for c, _ in cols]
        bases = _base_columns(spec, names)
        result = TableResult(
            table=f"{schema}.{spec.name}",
            base_columns=bases,
            min_cell=min_cell if bases else None,
            columns=[{"name": c, "type": t} for c, t in cols],
        )
        keep = sql.SQL(" AND ").join(
            sql.SQL("{c} >= {m}").format(c=sql.Identifier(b), m=sql.Literal(min_cell))
            for b in bases
        )
        user_filter = sql.SQL(spec.where) if spec.where else sql.SQL("true")
        relation = sql.Identifier(schema, spec.name)
        if bases:
            result.suppressed_rows = conn.execute(
                sql.SQL("SELECT count(*) FROM {r} WHERE ({w}) AND NOT coalesce({k}, false)").format(
                    r=relation, w=user_filter, k=keep
                )
            ).fetchone()[0]
        order = spec.order_by or names
        query = sql.SQL("SELECT {cols} FROM {r} WHERE ({w}) AND {k} ORDER BY {o}").format(
            cols=sql.SQL(", ").join(map(sql.Identifier, names)),
            r=relation,
            w=user_filter,
            k=keep if bases else sql.SQL("true"),
            o=sql.SQL(", ").join(map(sql.Identifier, order)),
        )
        stem = spec.file_name or spec.name
        writers = _Writers(self.out_dir, stem, defaults.formats, cols)
        try:
            with conn.cursor(name=f"dh_export_{stem}") as cur:
                cur.itersize = BATCH
                cur.execute(query)
                while batch := cur.fetchmany(BATCH):
                    writers.write(batch)
                    result.rows += len(batch)
            result.files = writers.close(defaults.max_file_mb)
        except BaseException:
            writers.abort()
            raise
        log.info(
            "tabela exportada",
            extra={
                "table": result.table,
                "rows": result.rows,
                "suppressed": result.suppressed_rows,
            },
        )
        return result


class _Writers:
    def __init__(
        self, out_dir: Path, stem: str, formats: list[str], cols: list[tuple[str, str]]
    ) -> None:
        self.out_dir = out_dir
        self.stem = stem
        self.names = [c for c, _ in cols]
        self.schema = pa.schema([(c, _arrow_type(t)) for c, t in cols])
        self.tmp: dict[str, Path] = {}
        self.csv_fh = None
        self.csv_writer = None
        self.parquet: pq.ParquetWriter | None = None
        if "csv" in formats:
            self.tmp["csv"] = self._tmp(".csv")
            self.csv_fh = self.tmp["csv"].open("w", encoding="utf-8", newline="")
            self.csv_writer = csv.writer(self.csv_fh, lineterminator="\n")
            self.csv_writer.writerow(self.names)
        if "parquet" in formats:
            self.tmp["parquet"] = self._tmp(".parquet")
            self.parquet = pq.ParquetWriter(self.tmp["parquet"], self.schema, compression="zstd")

    def _tmp(self, suffix: str) -> Path:
        fd, name = tempfile.mkstemp(dir=self.out_dir, prefix=".tmp_", suffix=suffix)
        os.close(fd)
        return Path(name)

    def write(self, batch: list[tuple]) -> None:
        if self.csv_writer:
            self.csv_writer.writerows([_csv_value(v) for v in row] for row in batch)
        if self.parquet:
            arrays = [
                pa.array([_arrow_value(row[i], f.type) for row in batch], type=f.type)
                for i, f in enumerate(self.schema)
            ]
            self.parquet.write_table(pa.Table.from_arrays(arrays, schema=self.schema))

    def close(self, max_mb: float) -> list[dict[str, Any]]:
        if self.csv_fh:
            self.csv_fh.close()
        if self.parquet:
            self.parquet.close()
        files = []
        for fmt, tmp in self.tmp.items():
            size = tmp.stat().st_size
            if size > max_mb * 1024 * 1024:
                self.abort()
                raise ExportError(
                    f"{self.stem}.{fmt} teria {size / 1048576:.1f} MB (limite {max_mb} MB): "
                    "agregue mais a tabela antes de exportar"
                )
            final = self.out_dir / f"{self.stem}.{fmt}"
            tmp.chmod(0o644)
            os.replace(tmp, final)
            files.append({"file": final.name, "bytes": size, "sha256": _sha256(final)})
        self.tmp = {}
        return files

    def abort(self) -> None:
        for handle in (self.csv_fh,):
            if handle and not handle.closed:
                handle.close()
        if self.parquet:
            try:
                self.parquet.close()
            except Exception:
                log.debug("parquet já fechado")
        for tmp in self.tmp.values():
            tmp.unlink(missing_ok=True)
        self.tmp = {}


def _atomic_text(path: Path, content: str) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content + "\n")
    Path(name).chmod(0o644)
    os.replace(name, path)
