from __future__ import annotations

from datetime import UTC, datetime

import fsspec
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from datahack_ingest.normalize import row_hash


class ParquetSink:
    def __init__(self, lake_uri: str, table: str, strategy: str, run_id: str) -> None:
        self.base = f"{lake_uri.rstrip('/')}/bronze/{table}"
        self.strategy = strategy
        self.run_id = run_id
        self.fs, self.root = fsspec.core.url_to_fs(self.base)
        self._seq = 0

    def prepare(self) -> None:
        self.fs.makedirs(self.root, exist_ok=True)

    def truncate(self) -> None:
        if self.fs.exists(self.root):
            self.fs.rm(self.root, recursive=True)
        self.fs.makedirs(self.root, exist_ok=True)

    def begin_unit(self) -> None:
        return None

    def write(self, frame: pd.DataFrame, unit_key: str) -> int:
        if frame.empty:
            return 0
        now = datetime.now(UTC)
        out = frame.copy()
        out["_dh_batch_id"] = self.run_id
        out["_dh_ingested_at"] = now.isoformat()
        out["_dh_source_file"] = unit_key
        out["_dh_row_hash"] = row_hash(frame)
        table = pa.Table.from_pandas(
            out, preserve_index=False, schema=pa.schema([(c, pa.string()) for c in out.columns])
        )
        part = f"{self.root}/ingest_date={now:%Y-%m-%d}"
        self.fs.makedirs(part, exist_ok=True)
        self._seq += 1
        with self.fs.open(f"{part}/{self.run_id}-{self._seq:05d}.parquet", "wb") as f:
            pq.write_table(table, f, compression="zstd")
        return len(out)

    def end_unit(self) -> tuple[int, int]:
        return -1, 0
