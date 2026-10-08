from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from fnmatch import fnmatch
from itertools import islice
from typing import IO, Any

import fastavro
import fsspec
import ijson
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from defusedxml.ElementTree import iterparse
from fsspec.utils import infer_compression
from openpyxl import load_workbook
from pyarrow import orc

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
Opener = Callable[[], Any]


def resolve_uri(landing_uri: str, path: str) -> str:
    if "://" in path or os.path.isabs(path):
        return path
    return f"{landing_uri.rstrip('/')}/{path.lstrip('/')}"


def _seekable(f: IO[bytes]) -> IO[bytes]:
    try:
        if f.seekable():
            return f
    except (AttributeError, OSError):
        pass
    return io.BytesIO(f.read())


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else str(tag)


def _xml_to_dict(elem) -> dict[str, Any]:
    out: dict[str, Any] = {_local(k): v for k, v in elem.attrib.items()}
    for child in elem:
        name = _local(child.tag)
        if len(child) or child.attrib:
            value: Any = _xml_to_dict(child)
            text = (child.text or "").strip()
            if text:
                value["value"] = text
        else:
            value = (child.text or "").strip() or None
        if name in out:
            existing = out[name]
            out[name] = [*existing, value] if isinstance(existing, list) else [existing, value]
        else:
            out[name] = value
    text = (elem.text or "").strip()
    if text and not len(elem):
        out["value"] = text
    return out


def _chunks(iterable, size: int) -> Iterator[list]:
    it = iter(iterable)
    while batch := list(islice(it, size)):
        yield batch


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

    def _is_zip(self, path: str) -> bool:
        comp = self.opts.compression
        return comp == "zip" or (comp == "infer" and path.lower().endswith(".zip"))

    def _compression(self, path: str) -> str | None:
        comp = self.opts.compression
        if comp == "none":
            return None
        if comp == "infer":
            return infer_compression(path)
        return comp

    def _openers(self, fs: fsspec.AbstractFileSystem, path: str) -> Iterator[tuple[str, Opener]]:
        if not self._is_zip(path):
            compression = self._compression(path)
            yield path, lambda: fs.open(path, "rb", compression=compression)
            return
        with fs.open(path, "rb") as raw:
            members = sorted(
                n
                for n in zipfile.ZipFile(raw).namelist()
                if not n.endswith("/") and fnmatch(n, self.opts.zip_member_pattern)
            )
        if not members:
            raise FileNotFoundError(
                f"{self.source.name}: zip {path} sem membros para '{self.opts.zip_member_pattern}'"
            )
        for member in members:

            @contextmanager
            def opener(m=member):
                with (
                    fs.open(path, "rb") as raw_zip,
                    zipfile.ZipFile(raw_zip) as zf,
                    zf.open(m) as f,
                ):
                    yield f

            yield f"{path}!{member}", opener

    def _read(self, fs: fsspec.AbstractFileSystem, path: str) -> Iterator[pd.DataFrame]:
        reader = {
            "csv": self._read_csv,
            "jsonl": self._read_jsonl,
            "json": self._read_json,
            "parquet": self._read_parquet,
            "xlsx": self._read_xlsx,
            "xml": self._read_xml,
            "fixed_width": self._read_fixed_width,
            "avro": self._read_avro,
            "orc": self._read_orc,
        }[self.opts.format]
        for _, opener in self._openers(fs, path):
            yield from reader(opener)

    def _read_csv(self, opener: Opener) -> Iterator[pd.DataFrame]:
        with opener() as f:
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

    def _read_fixed_width(self, opener: Opener) -> Iterator[pd.DataFrame]:
        with opener() as f:
            yield from pd.read_fwf(
                f,
                widths=self.opts.widths,
                names=self.opts.names,
                header=None if self.opts.names else 0,
                encoding=self.opts.encoding,
                encoding_errors="replace",
                skiprows=self.opts.skip_rows,
                dtype=str,
                keep_default_na=False,
                na_values=[""],
                chunksize=self.source.chunk_size,
            )

    def _read_jsonl(self, opener: Opener) -> Iterator[pd.DataFrame]:
        def records():
            with opener() as f:
                for raw in f:
                    line = raw.decode(self.opts.encoding, errors="replace").strip()
                    if line:
                        yield json.loads(line)

        for batch in _chunks(records(), self.source.chunk_size):
            yield records_to_frame(batch, self.opts.flatten_max_level)

    def _read_json(self, opener: Opener) -> Iterator[pd.DataFrame]:
        prefix = f"{self.opts.records_path}.item" if self.opts.records_path else "item"
        yielded = False
        with opener() as f:
            for batch in _chunks(ijson.items(f, prefix), self.source.chunk_size):
                yielded = True
                yield records_to_frame(batch, self.opts.flatten_max_level)
        if yielded:
            return
        with opener() as f:
            data = json.loads(f.read().decode(self.opts.encoding, errors="replace"))
        records = get_path(data, self.opts.records_path)
        if isinstance(records, dict):
            records = [records]
        if records is None:
            return
        if not isinstance(records, list):
            raise ValueError(f"{self.source.name}: records_path não aponta para uma lista")
        for batch in _chunks(records, self.source.chunk_size):
            yield records_to_frame(batch, self.opts.flatten_max_level)

    def _read_xml(self, opener: Opener) -> Iterator[pd.DataFrame]:
        tag = self.opts.record_tag

        def records():
            with opener() as f:
                root = None
                for event, elem in iterparse(f, events=("start", "end")):
                    if root is None and event == "start":
                        root = elem
                    if event == "end" and _local(elem.tag) == tag:
                        yield _xml_to_dict(elem)
                        elem.clear()
                        if root is not None:
                            root.clear()

        for batch in _chunks(records(), self.source.chunk_size):
            yield records_to_frame(batch, self.opts.flatten_max_level)

    def _read_avro(self, opener: Opener) -> Iterator[pd.DataFrame]:
        with opener() as f:
            for batch in _chunks(fastavro.reader(f), self.source.chunk_size):
                yield records_to_frame(batch, self.opts.flatten_max_level)

    def _read_parquet(self, opener: Opener) -> Iterator[pd.DataFrame]:
        with opener() as f:
            pf = pq.ParquetFile(_seekable(f))
            for batch in pf.iter_batches(batch_size=self.source.chunk_size):
                yield _arrow_to_text_frame(batch)

    def _read_orc(self, opener: Opener) -> Iterator[pd.DataFrame]:
        with opener() as f:
            reader = orc.ORCFile(_seekable(f))
            for i in range(reader.nstripes):
                table = reader.read_stripe(i)
                for batch in pa.Table.from_batches([table]).to_batches(self.source.chunk_size):
                    yield _arrow_to_text_frame(batch)

    def _read_xlsx(self, opener: Opener) -> Iterator[pd.DataFrame]:
        with opener() as f:
            wb = load_workbook(_seekable(f), read_only=True, data_only=True)
            try:
                sheet = self.opts.sheet_name
                ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
                rows = ws.iter_rows(values_only=True)
                for _ in range(self.opts.skip_rows):
                    next(rows, None)
                header = next(rows, None)
                if header is None:
                    return
                columns = [
                    str(h) if h is not None and str(h).strip() else f"col_{i + 1}"
                    for i, h in enumerate(header)
                ]
                width = len(columns)
                for batch in _chunks(rows, self.source.chunk_size):
                    data = [
                        [to_text(v) for v in (list(r) + [None] * width)[:width]]
                        for r in batch
                        if any(v is not None for v in r)
                    ]
                    if data:
                        yield pd.DataFrame(data, columns=columns, dtype=object)
            finally:
                wb.close()


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
