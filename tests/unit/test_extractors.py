import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

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


class _Api(BaseHTTPRequestHandler):
    calls: list = []

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        _Api.calls.append({"q": q, "auth": self.headers.get("Authorization")})
        items = [{"id": i} for i in range(3)]
        body = json.dumps({"data": items}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def test_api_get_with_records_path_and_chunks():
    server = HTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/v1/itens"
        src = _source(
            {
                "name": "a",
                "kind": "api",
                "chunk_size": 100,
                "api": {"url": url, "records_path": "data", "params": {"v": "93"}},
            }
        )
        _Api.calls = []
        _, df = _collect(build_extractor(src, ""), ExtractState())
        assert df["id"].tolist() == ["0", "1", "2"]
        assert len(_Api.calls) == 1
        assert _Api.calls[0]["q"] == {"v": ["93"]}
    finally:
        server.shutdown()
