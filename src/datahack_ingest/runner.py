from __future__ import annotations

import logging
import os
import statistics
import time
import uuid
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
import psycopg

from datahack_ingest.alerting import Alert, send_alert
from datahack_ingest.catalog import ApiSource, FileSource, SqlSource
from datahack_ingest.extractors import ExtractState, build_extractor
from datahack_ingest.normalize import normalize_identifier, to_text_frame
from datahack_ingest.settings import Settings
from datahack_ingest.sinks import ParquetSink, PostgresSink
from datahack_ingest.state import StateStore, parse_watermark, record_file, set_watermark
from datahack_ingest.transforms import apply_transforms

log = logging.getLogger(__name__)
AnySource = FileSource | ApiSource | SqlSource


class SourceLockedError(RuntimeError):
    pass


class VolumeAnomalyError(RuntimeError):
    pass


@dataclass
class RunResult:
    source: str
    run_id: str
    status: str = "running"
    units_processed: int = 0
    units_skipped: int = 0
    rows_extracted: int = 0
    rows_filtered: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    rows_deleted: int = 0
    watermark_from: str | None = None
    watermark_to: str | None = None
    new_columns: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
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


def _prepare_frame(source: AnySource, raw: pd.DataFrame, result: RunResult) -> pd.DataFrame:
    frame = to_text_frame(raw)
    result.rows_extracted += len(frame)
    if source.transforms:
        before = len(frame)
        frame = to_text_frame(apply_transforms(frame, source.transforms))
        result.rows_filtered += before - len(frame)
    result.columns = sorted(set(result.columns) | set(frame.columns))
    return frame


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
        send_alert(
            Alert(
                title=f"Falha na ingestão: {source.name}",
                message=result.error,
                severity="error",
                context={"run_id": run_id, "orchestrator_run_id": orchestrator_run_id},
            )
        )
        raise
    finally:
        result.duration_s = round(time.monotonic() - started, 3)
        if locked:
            state.finish_run(run_id, result.status, result.as_dict(), result.error)
            state.unlock(source.name)
        ctrl.close()
        log.info("fim da ingestão", extra={**ctx, **_summary(result)})
    return result


def _check_volume(source: AnySource, state: StateStore, result: RunResult) -> None:
    vc = source.volume_check
    if not vc or result.units_processed == 0:
        return
    history = state.recent_volumes(source.name, vc.lookback_runs)
    if len(history) < vc.min_history:
        return
    baseline = statistics.median(history)
    current = result.rows_extracted
    ratio = current / baseline if baseline else (float("inf") if current else 1.0)
    if vc.min_ratio <= ratio <= vc.max_ratio:
        return
    severity = "error" if vc.action == "fail" else "warning"
    detail = {
        "rows_extracted": current,
        "median_baseline": baseline,
        "ratio": round(ratio, 4) if ratio != float("inf") else None,
        "min_ratio": vc.min_ratio,
        "max_ratio": vc.max_ratio,
        "history": history,
    }
    message = (
        f"{source.name}: volume fora do esperado ({current} linhas; mediana {baseline:.0f}; "
        f"faixa aceita {vc.min_ratio}x a {vc.max_ratio}x)"
    )
    state.record_event(source.name, result.run_id, "volume", severity, detail)
    result.warnings.append(message)
    if vc.action == "fail":
        raise VolumeAnomalyError(message)
    send_alert(
        Alert(
            title=f"Volume anômalo: {source.name}",
            message=message,
            severity="warning",
            context={"run_id": result.run_id},
        )
    )


def _extract_state(source: AnySource, state: StateStore, result: RunResult) -> ExtractState:
    wm_stored = state.get_watermark(source.name) if _supports_watermark(source) else None
    extract_state = ExtractState(strategy=source.load_strategy)
    if wm_stored:
        result.watermark_from = wm_stored[0]
        extract_state.watermark = parse_watermark(*wm_stored)
    if isinstance(source, FileSource) and source.load_strategy != "full":
        if source.delete_detection:
            extract_state.loaded_file_hashes = state.last_file_hash(source.name)
        else:
            extract_state.loaded_file_hashes = state.loaded_file_hashes(source.name)
    return extract_state


def _execute(source: AnySource, settings: Settings, state: StateStore, result: RunResult) -> None:
    extract_state = _extract_state(source, state, result)

    extractor = build_extractor(source, settings.landing_uri)
    tracker = _WatermarkTracker(source.watermark_column, source.watermark_type)
    uses_keys_query = bool(
        source.delete_detection and source.delete_detection.scope == "keys_query"
    )

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
                        frame = _prepare_frame(source, raw, result)
                        tracker.observe(frame)
                        copied += sink.write(frame, unit.key)
                    if uses_keys_query:
                        sink.load_keys(to_text_frame(f) for f in extractor.key_frames())
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
            if full:
                _check_volume(source, state, result)
        if not full:
            _check_volume(source, state, result)
        result.units_skipped = getattr(extractor, "skipped", 0)
        result.rows_deleted = getattr(sink, "rows_deleted", 0)
        result.watermark_to = tracker.as_text() or result.watermark_from
        result.new_columns = list(getattr(sink, "new_columns", []))


def _build_sink(source: AnySource, settings: Settings, conn: psycopg.Connection, run_id: str):
    if source.sink == "parquet":
        return ParquetSink(settings.lake_uri, source.table, source.load_strategy, run_id)
    return PostgresSink(
        conn,
        source.name,
        source.table,
        source.load_strategy,
        source.primary_key,
        run_id,
        delete_detection=source.delete_detection,
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
            _prepare_frame(source, raw, result)
    result.status = "dry_run"
    result.duration_s = round(time.monotonic() - started, 3)
    return result


def _summary(r: RunResult) -> dict[str, Any]:
    keys = (
        "status",
        "units_processed",
        "rows_extracted",
        "rows_filtered",
        "rows_loaded",
        "rows_rejected",
        "rows_deleted",
        "duration_s",
    )
    return {k: getattr(r, k) for k in keys}
