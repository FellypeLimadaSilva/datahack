from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Iterator

import fsspec
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from datahack_ingest.catalog import FileSource
from datahack_ingest.extractors.base import (
    ExtractState,
    ExtractUnit,
    get_path,
    records_to_frame,
)
from datahack_ingest.normalize import to_text

log = logging.getLogger(__name__)
_HASH_BLOCK = 8 * 1024 * 1024


def resolve_uri(landing_uri: str, path: str) -> str:
    if "://" in path or os.path.isabs(path):
        return path
    return f"{landing_uri.rstrip('/')}/{path.lstrip('/')}"


class FileExtractor:
    def __init__(self, source: FileSource, landing_uri: str) -> None:
        self.source = source
        self.opts = source.file
        self.urlpath = resolve_uri(landing_uri, self.opts.path)
        self.skipped = 0

    def list_files(self) -> tuple[fsspec.AbstractFileSystem, list[str]]:
        fs, _, paths = fsspec.get_fs_token_paths(self.urlpath)
        files = sorted(p for p in paths if fs.isfile(p))
        return fs, files

    def units(self, state: ExtractState) -> Iterator[ExtractUnit]:
        fs, files = self.list_files()
        if not files:
            if state.strategy == "full":
                raise FileNotFoundError(
                    f"{self.source.name}: nenhum arquivo em {self.urlpath}; "
                    "carga full abortada para não esvaziar a Bronze."
                )
            log.warning("nenhum arquivo encontrado", extra={"urlpath": self.urlpath})
            return
        for path in files:
            digest, size = self._digest(fs, path)
            if state.strategy != "full" and digest in state.loaded_file_hashes:
                log.info("arquivo já carregado (idempotência)", extra={"file": path})
                self.skipped += 1
                continue
            yield ExtractUnit(
                key=fs.unstrip_protocol(path),
                frames=self._read(fs, path),
                file_sha256=digest,
                file_size=size,
            )

    @staticmethod
    def _digest(fs: fsspec.AbstractFileSystem, path: str) -> tuple[str, int]:
        h = hashlib.sha256()
        size = 0
        with fs.open(path, "rb") as f:
            while block := f.read(_HASH_BLOCK):
                h.update(block)
                size += len(block)
        return h.hexdigest(), size

    def _read(self, fs: fsspec.AbstractFileSystem, path: str) -> Iterator[pd.DataFrame]:
        reader = {
            "csv": self._read_csv,
            "jsonl": self._read_jsonl,
            "json": self._read_json,
            "parquet": self._read_parquet,
            "xlsx": self._read_xlsx,
        }[self.opts.format]
        with fs.open(path, "rb") as f:
            yield from reader(f)

    def _read_csv(self, f) -> Iterator[pd.DataFrame]:
        yield from pd.read_csv(
            f,
            sep=self.opts.sep,
            encoding=self.opts.encoding,
            encoding_errors="replace",
            quotechar=self.opts.quotechar,
            skiprows=self.opts.skip_rows,
            dtype=str,
            keep_default_na=False,
            na_values=[""],
            chunksize=self.source.chunk_size,
        )

    def _read_jsonl(self, f) -> Iterator[pd.DataFrame]:
        buffer: list = []
        for raw in f:
            line = raw.decode(self.opts.encoding, errors="replace").strip()
            if not line:
                continue
            buffer.append(json.loads(line))
            if len(buffer) >= self.source.chunk_size:
                yield records_to_frame(buffer, self.opts.flatten_max_level)
                buffer = []
        if buffer:
            yield records_to_frame(buffer, self.opts.flatten_max_level)

    def _read_json(self, f) -> Iterator[pd.DataFrame]:
        data = json.loads(f.read().decode(self.opts.encoding, errors="replace"))
        records = get_path(data, self.opts.records_path)
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list):
            raise ValueError(f"{self.source.name}: records_path não aponta para uma lista")
        step = self.source.chunk_size
        for i in range(0, len(records), step):
            yield records_to_frame(records[i : i + step], self.opts.flatten_max_level)

    def _read_parquet(self, f) -> Iterator[pd.DataFrame]:
        pf = pq.ParquetFile(f)
        for batch in pf.iter_batches(batch_size=self.source.chunk_size):
            yield _arrow_to_text_frame(batch)

    def _read_xlsx(self, f) -> Iterator[pd.DataFrame]:
        df = pd.read_excel(
            f, sheet_name=self.opts.sheet_name, dtype=str, skiprows=self.opts.skip_rows
        )
        step = self.source.chunk_size
        for i in range(0, len(df), step):
            yield df.iloc[i : i + step]


def _arrow_to_text_frame(batch: pa.RecordBatch) -> pd.DataFrame:
    columns: dict[str, list] = {}
    for name, col in zip(batch.schema.names, batch.columns, strict=True):
        t = col.type
        if pa.types.is_nested(t) or pa.types.is_binary(t) or pa.types.is_large_binary(t):
            columns[name] = [to_text(v) for v in col.to_pylist()]
        else:
            try:
                columns[name] = pc.cast(col, pa.string()).to_pylist()
            except (pa.ArrowNotImplementedError, pa.ArrowInvalid):
                columns[name] = [to_text(v) for v in col.to_pylist()]
    return pd.DataFrame(columns, dtype=object)
