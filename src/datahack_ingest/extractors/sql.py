from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from queue import Empty, Full, Queue
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from datahack_ingest.catalog import SqlSource
from datahack_ingest.extractors.base import ExtractState, ExtractUnit

_DONE = object()


class SqlExtractor:
    def __init__(self, source: SqlSource) -> None:
        self.source = source
        self.opts = source.sql

    def _url(self) -> str:
        url = os.environ.get(self.opts.url_env)
        if not url:
            raise OSError(f"variável de ambiente obrigatória ausente: {self.opts.url_env}")
        return url

    def _engine(self) -> Engine:
        size = self.opts.partition.num_partitions if self.opts.partition else 1
        return create_engine(self._url(), pool_pre_ping=True, pool_size=size, max_overflow=0)

    def _base(self) -> str:
        return self.opts.query or f"SELECT * FROM {self.opts.table}"

    def _conditions(self, state: ExtractState) -> tuple[list[str], dict[str, Any]]:
        wm_col = self.source.watermark_column
        if not wm_col or state.watermark is None:
            return [], {}
        op = ">=" if self.source.load_strategy == "merge" else ">"
        return [f"{wm_col} {op} :dh_wm"], {"dh_wm": state.watermark}

    def build_query(self, state: ExtractState, extra: list[str] | None = None) -> tuple[str, dict]:
        conditions, params = self._conditions(state)
        conditions += extra or []
        if not conditions:
            return self._base(), params
        sql = f"SELECT * FROM ({self._base()}) dh_src WHERE {' AND '.join(conditions)}"
        if self.source.watermark_column and not extra:
            sql += f" ORDER BY {self.source.watermark_column}"
        return sql, params

    def units(self, state: ExtractState) -> Iterator[ExtractUnit]:
        yield ExtractUnit(key=f"sql:{self.source.name}", frames=self._frames(state))

    def _stream(self, engine: Engine, sql: str, params: dict) -> Iterator[pd.DataFrame]:
        with engine.connect() as conn:
            result = conn.execution_options(
                stream_results=True, yield_per=self.source.chunk_size
            ).execute(text(sql), params)
            columns = list(result.keys())
            for rows in result.partitions(self.source.chunk_size):
                yield pd.DataFrame([tuple(r) for r in rows], columns=columns, dtype=object)

    def _frames(self, state: ExtractState) -> Iterator[pd.DataFrame]:
        engine = self._engine()
        try:
            if self.opts.partition:
                yield from self._parallel_frames(engine, state)
            else:
                sql, params = self.build_query(state)
                yield from self._stream(engine, sql, params)
        finally:
            engine.dispose()

    def _bounds(self, engine: Engine, state: ExtractState) -> tuple[int, int] | None:
        part = self.opts.partition
        if part.lower_bound is not None and part.upper_bound is not None:
            return part.lower_bound, part.upper_bound
        conditions, params = self._conditions(state)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT MIN({part.column}), MAX({part.column}) FROM ({self._base()}) dh_src{where}"
        with engine.connect() as conn:
            lo, hi = conn.execute(text(sql), params).one()
        if lo is None or hi is None:
            return None
        lo = int(lo) if part.lower_bound is None else part.lower_bound
        hi = int(hi) if part.upper_bound is None else part.upper_bound
        return lo, hi

    @staticmethod
    def ranges(lo: int, hi: int, n: int) -> list[tuple[int, int]]:
        span = hi - lo + 1
        n = max(1, min(n, span))
        step = -(-span // n)
        out = []
        start = lo
        while start <= hi:
            end = min(start + step, hi + 1)
            out.append((start, end))
            start = end
        return out

    def _parallel_frames(self, engine: Engine, state: ExtractState) -> Iterator[pd.DataFrame]:
        part = self.opts.partition
        bounds = self._bounds(engine, state)
        if bounds is None:
            return
        slices = self.ranges(*bounds, part.num_partitions)
        queue: Queue = Queue(maxsize=part.num_partitions * 2)
        stop = threading.Event()

        def put(item: Any) -> None:
            while not stop.is_set():
                try:
                    queue.put(item, timeout=0.5)
                    return
                except Full:
                    continue

        def worker(lo: int, hi_exclusive: int) -> None:
            sql, params = self.build_query(
                state, [f"{part.column} >= :dh_lo", f"{part.column} < :dh_hi"]
            )
            params = {**params, "dh_lo": lo, "dh_hi": hi_exclusive}
            try:
                for frame in self._stream(engine, sql, params):
                    if stop.is_set():
                        return
                    put(frame)
            except BaseException as exc:
                put(exc)
            finally:
                put(_DONE)

        threads = [
            threading.Thread(target=worker, args=s, daemon=True, name=f"dh-sql-{i}")
            for i, s in enumerate(slices)
        ]
        for t in threads:
            t.start()
        finished = 0
        try:
            while finished < len(threads):
                try:
                    item = queue.get(timeout=1)
                except Empty:
                    continue
                if item is _DONE:
                    finished += 1
                elif isinstance(item, BaseException):
                    raise item
                else:
                    yield item
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=5)

    def key_frames(self) -> Iterator[pd.DataFrame]:
        query = self.source.delete_detection.keys_query
        engine = self._engine()
        try:
            yield from self._stream(engine, query, {})
        finally:
            engine.dispose()
