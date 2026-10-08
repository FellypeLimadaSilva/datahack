import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sqlalchemy import create_engine, text

from datahack_ingest.catalog import Catalog
from datahack_ingest.extractors import ExtractState, build_extractor
from datahack_ingest.extractors.base import flatten_record
from datahack_ingest.normalize import to_text_frame


def _source(spec: dict):
    return Catalog.model_validate({"sources": [spec]}).sources[0]


def _collect(extractor, state=None):
    state = state or ExtractState()
    units = list(extractor.units(state))
    frames = [to_text_frame(f) for u in units for f in u.frames]
    return units, (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())


def test_flatten_respects_max_level_and_keeps_ints():
    rec = {"id": 1, "cat": {"dep": "Moda", "sub": {"x": 1}}, "tags": ["a"], "v": None}
    assert flatten_record(rec, max_level=1) == {
        "id": "1",
        "cat_dep": "Moda",
        "cat_sub": '{"x": 1}',
        "tags": '["a"]',
        "v": None,
    }


def test_csv_chunked_with_sep_and_idempotency(tmp_path):
    (tmp_path / "a.csv").write_text("id;nome\n1;x\n2;\n3;z\n", encoding="utf-8")
    src = _source(
        {
            "name": "c",
            "kind": "file",
            "chunk_size": 100,
            "file": {"path": "a.csv", "format": "csv", "sep": ";"},
        }
    )
    ext = build_extractor(src, str(tmp_path))
    units, df = _collect(ext)
    assert len(units) == 1 and units[0].file_sha256
    assert df["nome"].tolist() == ["x", None, "z"]
    again, _ = _collect(ext, ExtractState(loaded_file_hashes={units[0].file_sha256}))
    assert again == [] and ext.skipped == 1


def test_full_strategy_without_files_fails_safe(tmp_path):
    src = _source(
        {
            "name": "c",
            "kind": "file",
            "load_strategy": "full",
            "file": {"path": "nada/*.csv", "format": "csv"},
        }
    )
    with pytest.raises(FileNotFoundError):
        list(build_extractor(src, str(tmp_path)).units(ExtractState(strategy="full")))


def test_parquet_ints_with_nulls_stay_ints(tmp_path):
    table = pa.table(
        {"id": pa.array([1, None, 3], pa.int64()), "ts": pa.array([0, 1, 2], pa.timestamp("s"))}
    )
    pq.write_table(table, tmp_path / "p.parquet")
    src = _source(
        {
            "name": "p",
            "kind": "file",
            "chunk_size": 100,
            "file": {"path": "p.parquet", "format": "parquet"},
        }
    )
    _, df = _collect(build_extractor(src, str(tmp_path)))
    assert df["id"].tolist() == ["1", None, "3"]
    assert df["ts"].iloc[0].startswith("1970-01-01 00:00:00")


def test_jsonl_and_json_records_path(tmp_path):
    (tmp_path / "e.jsonl").write_text('{"a": 1}\n\n{"a": 2, "b": {"c": "x"}}\n', encoding="utf-8")
    src = _source(
        {
            "name": "j",
            "kind": "file",
            "chunk_size": 100,
            "file": {"path": "e.jsonl", "format": "jsonl"},
        }
    )
    _, df = _collect(build_extractor(src, str(tmp_path)))
    assert df["a"].tolist() == ["1", "2"] and df["b_c"].tolist()[1] == "x"

    (tmp_path / "d.json").write_text(
        json.dumps({"data": {"items": [{"k": 1}, {"k": 2}]}}), encoding="utf-8"
    )
    src = _source(
        {
            "name": "d",
            "kind": "file",
            "chunk_size": 100,
            "file": {"path": "d.json", "format": "json", "records_path": "data.items"},
        }
    )
    _, df = _collect(build_extractor(src, str(tmp_path)))
    assert df["k"].tolist() == ["1", "2"]


class _Api(BaseHTTPRequestHandler):
    calls: list = []

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        _Api.calls.append({"q": q, "auth": self.headers.get("Authorization")})
        page = int(q.get("page", ["1"])[0])
        items = [{"id": i} for i in range((page - 1) * 2, (page - 1) * 2 + 2)] if page <= 2 else []
        if page == 2:
            items = items[:1]
        body = json.dumps({"data": items}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def test_api_paginates_with_bearer_and_incremental_param(monkeypatch):
    monkeypatch.setenv("TEST_TOKEN", "segredo")
    server = HTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/v1/itens"
        src = _source(
            {
                "name": "a",
                "kind": "api",
                "chunk_size": 100,
                "api": {
                    "url": url,
                    "records_path": "data",
                    "incremental_param": "since",
                    "auth": {"type": "bearer", "token_env": "TEST_TOKEN"},
                    "pagination": {"type": "page", "page_size": 2, "size_param": "per_page"},
                },
            }
        )
        _Api.calls = []
        _, df = _collect(build_extractor(src, ""), ExtractState(watermark="2026-01-01"))
        assert df["id"].tolist() == ["0", "1", "2"]
        assert len(_Api.calls) == 2
        assert _Api.calls[0]["auth"] == "Bearer segredo"
        assert _Api.calls[0]["q"]["since"] == ["2026-01-01"]
    finally:
        server.shutdown()


def test_sql_incremental_watermark(tmp_path, monkeypatch):
    db = tmp_path / "src.db"
    url = f"sqlite:///{db}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("create table t (id integer, v integer, upd integer)"))
        c.execute(text("insert into t values (1, null, 10), (2, 5, 20), (3, 7, 30)"))
    monkeypatch.setenv("SRC_URL", url)
    src = _source(
        {
            "name": "s",
            "kind": "sql",
            "chunk_size": 100,
            "watermark_column": "upd",
            "watermark_type": "integer",
            "sql": {"url_env": "SRC_URL", "table": "t"},
        }
    )
    _, df = _collect(build_extractor(src, ""), ExtractState(watermark=10))
    assert df["id"].tolist() == ["2", "3"]
    _, full = _collect(build_extractor(src, ""))
    assert full["v"].tolist()[0] is None
