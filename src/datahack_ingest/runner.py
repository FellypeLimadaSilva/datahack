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

from datahack_ingest.catalog import AnySource
from datahack_ingest.extractors import ExtractState, build_extractor
from datahack_ingest.normalize import to_text_frame
from datahack_ingest.settings import Settings
from datahack_ingest.sinks import PostgresSink
from datahack_ingest.state import StateStore, record_file
from datahack_ingest.transforms import apply_transforms

log = logging.getLogger(__name__)


class SourceLockedError(RuntimeError):
    pass


class VolumeAnomalyError(RuntimeError):
    pass


class MissingColumnsError(RuntimeError):
    pass


class EmptyFullLoadError(RuntimeError):
    pass


@dataclass
class RunResult:
    source: str
    run_id: str
    required: bool = True
    status: str = "running"
    units_processed: int = 0
    units_skipped: int = 0
    rows_extracted: int = 0
    rows_filtered: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    new_columns: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    result = RunResult(source=source.name, run_id=run_id, required=source.required)
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


def _check_essential(source: AnySource, unit_key: str, columns: set[str]) -> None:
    missing = [c for c in source.essential_columns if c not in columns]
    if missing:
        raise MissingColumnsError(
            f"{source.name}: {unit_key} sem colunas essenciais {missing}; carga revertida"
        )


def _execute(source: AnySource, settings: Settings, state: StateStore, result: RunResult) -> None:
    full = source.load_strategy == "full"
    extract_state = ExtractState(strategy=source.load_strategy)
    if not full:
        extract_state.loaded_file_hashes = state.loaded_file_hashes(source.name)
    extractor = build_extractor(source, settings.landing_uri)

    with psycopg.connect(settings.conninfo(), autocommit=True) as data:
        sink = PostgresSink(data, source.name, source.table, result.run_id)
        with data.transaction() if full else nullcontext():
            if full:
                sink.prepare()
                sink.truncate()
            for unit in extractor.units(extract_state):
                with nullcontext() if full else data.transaction():
                    if not full:
                        sink.prepare()
                    copied, seen = 0, set()
                    for raw in unit.frames:
                        frame = _prepare_frame(source, raw, result)
                        seen.update(frame.columns)
                        copied += sink.write(frame, unit.key)
                    if copied:
                        _check_essential(source, unit.key, seen)
                    result.rows_loaded += copied
                    if unit.file_sha256:
                        record_file(data, source.name, unit, copied, result.run_id)
                    _record_schema_changes(data, sink, source, result.run_id)
                    result.units_processed += 1
            if full and result.rows_loaded == 0:
                raise EmptyFullLoadError(
                    f"{source.name}: carga full sem linhas; versão anterior mantida"
                )
            _check_volume(source, state, result)
        result.units_skipped = getattr(extractor, "skipped", 0)
        deferred = getattr(extractor, "deferred", [])
        if deferred:
            result.warnings.append(
                f"{len(deferred)} arquivo(s) em gravação; entram na próxima execução"
            )
        result.new_columns = list(sink.new_columns)


def _record_schema_changes(conn, sink: PostgresSink, source: AnySource, run_id: str) -> None:
    pending = sink.new_columns
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
        "duration_s",
    )
    return {k: getattr(r, k) for k in keys}
