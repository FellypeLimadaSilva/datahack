from __future__ import annotations

import os
from collections.abc import Iterator

import pandas as pd
from sqlalchemy import create_engine, text

from datahack_ingest.catalog import SqlSource
from datahack_ingest.extractors.base import ExtractState, ExtractUnit


class SqlExtractor:
    def __init__(self, source: SqlSource) -> None:
        self.source = source
        self.opts = source.sql

    def _url(self) -> str:
        url = os.environ.get(self.opts.url_env)
        if not url:
            raise OSError(f"variável de ambiente obrigatória ausente: {self.opts.url_env}")
        return url

    def build_query(self, state: ExtractState) -> tuple[str, dict]:
        base = self.opts.query or f"SELECT * FROM {self.opts.table}"
        wm_col = self.source.watermark_column
        if not wm_col or state.watermark is None:
            return base, {}
        op = ">=" if self.source.load_strategy == "merge" else ">"
        sql = f"SELECT * FROM ({base}) dh_src WHERE {wm_col} {op} :dh_wm ORDER BY {wm_col}"
        return sql, {"dh_wm": state.watermark}

    def units(self, state: ExtractState) -> Iterator[ExtractUnit]:
        yield ExtractUnit(key=f"sql:{self.source.name}", frames=self._frames(state))

    def _frames(self, state: ExtractState) -> Iterator[pd.DataFrame]:
        sql, params = self.build_query(state)
        engine = create_engine(self._url(), pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                result = conn.execution_options(
                    stream_results=True, yield_per=self.source.chunk_size
                ).execute(text(sql), params)
                columns = list(result.keys())
                for rows in result.partitions(self.source.chunk_size):
                    yield pd.DataFrame([tuple(r) for r in rows], columns=columns, dtype=object)
        finally:
            engine.dispose()
