from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
import psycopg

from datahack_ingest.catalog import ApiSource, FileSource, SqlSource
from datahack_ingest.extractors import ExtractState, build_extractor
from datahack_ingest.normalize import normalize_identifier, to_text_frame
from datahack_ingest.settings import Settings
from datahack_ingest.sinks import ParquetSink, PostgresSink
from datahack_ingest.state import StateStore, parse_watermark, record_file, set_watermark

log = logging.getLogger(__name__)
AnySource = FileSource | ApiSource | SqlSource


class SourceLockedError(RuntimeError):
    pass


@dataclass
class RunResult:
    source: str
    run_id: str
    status: str = "running"
    units_processed: int = 0
    units_skipped: int = 0
    rows_extracted: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    watermark_from: str | None = None
    watermark_to: str | None = None
    new_columns: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class _WatermarkTracker:
    def __init__(self, column: str | None, vtype: str) -> None:
        self.column = normalize_identifier(column.replace(".", "_")) if column else None
        self.vtype = vtype
        self.value: Any = None

    def observe(self, frame: pd.DataFrame) -> None:
        if not self.column or self.column not in frame.columns:
            return
        s = frame[self.column]
        if self.vtype == "timestamp":
            parsed = pd.to_datetime(s, errors="coerce", format="mixed")
        elif self.vtype == "integer":
            parsed = pd.to_numeric(s, errors="coerce")
        else:
            parsed = s.dropna()
        if parsed.dropna().empty:
            return
        current = parsed.max()
        if self.value is None or current > self.value:
            self.value = current

    def as_text(self) -> str | None:
        if self.value is None:
            return None
        if self.vtype == "timestamp":
            return pd.Timestamp(self.value).isoformat()
        if self.vtype == "integer":
            return str(int(self.value))
        return str(self.value)


def _supports_watermark(source: AnySource) -> bool:
    return bool(source.watermark_column) and isinstance(source, ApiSource | SqlSource)


def run_source(
    source: AnySource,
    settings: Settings,
    run_id: str | None = None,
    orchestrator_run_id: str | None = None,
    dry_run: bool = False,
) -> RunResult:
    run_id = run_id or str(uuid.uuid4())
    orchestrator_run_id = orchestrator_run_id or os.environ.get("AIRFLOW_CTX_DAG_RUN_ID")
    result = RunResult(source=source.name, run_id=run_id)
    started = time.monotonic()
    ctx = {"source": source.name, "run_id": run_id}
    log.info("início da ingestão", extra={**ctx, "strategy": source.load_strategy})

    if dry_run:
        return _dry_run(source, settings, result, started)

    ctrl = psycopg.connect(settings.conninfo(), autocommit=True)
    state = StateStore(ctrl)
    locked = False
    try:
        state.ensure()
        locked = state.try_lock(source.name)
        if not locked:
            raise SourceLockedError(f"{source.name}: já existe execução em andamento")
        state.start_run(run_id, source, orchestrator_run_id)
        _execute(source, settings, state, result)
        result.status = "success"
    except Exception as exc:
        result.status = "failed"
        result.error = f"{type(exc).__name__}: {exc}"
        log.exception("falha na ingestão", extra=ctx)
        raise
    finally:
        result.duration_s = round(time.monotonic() - started, 3)
        if locked:
            state.finish_run(run_id, result.status, result.as_dict(), result.error)
            state.unlock(source.name)
        ctrl.close()
        log.info("fim da ingestão", extra={**ctx, **_summary(result)})
    return result


def _execute(source: AnySource, settings: Settings, state: StateStore, result: RunResult) -> None:
    wm_stored = state.get_watermark(source.name) if _supports_watermark(source) else None
    extract_state = ExtractState(strategy=source.load_strategy)
    if wm_stored:
        result.watermark_from = wm_stored[0]
        extract_state.watermark = parse_watermark(*wm_stored)
    if isinstance(source, FileSource) and source.load_strategy != "full":
        extract_state.loaded_file_hashes = state.loaded_file_hashes(source.name)

    extractor = build_extractor(source, settings.landing_uri)
    tracker = _WatermarkTracker(source.watermark_column, source.watermark_type)

    with psycopg.connect(settings.conninfo(), autocommit=True) as data:
        sink = _build_sink(source, settings, data, result.run_id)
        full = source.load_strategy == "full"
        outer = data.transaction() if full else nullcontext()
        with outer:
            if full:
                sink.prepare()
                sink.truncate()
            for unit in extractor.units(extract_state):
                with nullcontext() if full else data.transaction():
                    if not full:
                        sink.prepare()
                    sink.begin_unit()
                    copied = 0
                    for raw in unit.frames:
                        frame = to_text_frame(raw)
                        result.columns = sorted(set(result.columns) | set(frame.columns))
                        result.rows_extracted += len(frame)
                        tracker.observe(frame)
                        copied += sink.write(frame, unit.key)
                    written, rejected = sink.end_unit()
                    written = copied if written < 0 else written
                    result.rows_loaded += written
                    result.rows_rejected += rejected
                    if unit.file_sha256:
                        record_file(data, source.name, unit, copied, result.run_id)
                    if _supports_watermark(source) and tracker.as_text():
                        set_watermark(
                            data,
                            source.name,
                            tracker.as_text(),
                            source.watermark_type,
                            result.run_id,
                        )
                    _record_schema_changes(data, sink, source, result.run_id)
                    result.units_processed += 1
        result.units_skipped = getattr(extractor, "skipped", 0)
        result.watermark_to = tracker.as_text() or result.watermark_from
        result.new_columns = list(getattr(sink, "new_columns", []))


def _build_sink(source: AnySource, settings: Settings, conn: psycopg.Connection, run_id: str):
    if source.sink == "parquet":
        return ParquetSink(settings.lake_uri, source.table, source.load_strategy, run_id)
    return PostgresSink(
        conn, source.name, source.table, source.load_strategy, source.primary_key, run_id
    )


def _record_schema_changes(conn, sink, source: AnySource, run_id: str) -> None:
    pending = getattr(sink, "new_columns", [])
    recorded = getattr(sink, "_recorded", 0)
    for col in pending[recorded:]:
        conn.execute(
            """INSERT INTO ops.schema_changes (source, table_name, column_name, run_id)
               VALUES (%s, %s, %s, %s)""",
            (source.name, source.table, col, run_id),
        )
    sink._recorded = len(pending)


def _dry_run(source: AnySource, settings: Settings, result: RunResult, started: float) -> RunResult:
    extractor = build_extractor(source, settings.landing_uri)
    for unit in extractor.units(ExtractState(strategy="full")):
        result.units_processed += 1
        for raw in unit.frames:
            frame = to_text_frame(raw)
            result.rows_extracted += len(frame)
            result.columns = sorted(set(result.columns) | set(frame.columns))
    result.status = "dry_run"
    result.duration_s = round(time.monotonic() - started, 3)
    return result


def _summary(r: RunResult) -> dict[str, Any]:
    keys = (
        "status",
        "units_processed",
        "rows_extracted",
        "rows_loaded",
        "rows_rejected",
        "duration_s",
    )
    return {k: getattr(r, k) for k in keys}
