import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from datahack_ingest.catalog import Catalog
from datahack_ingest.extractors import ExtractState, build_extractor
from datahack_ingest.extractors.api import GraphQLError
from datahack_ingest.extractors.sql import SqlExtractor
from datahack_ingest.normalize import to_text_frame


def _source(spec: dict):
    return Catalog.model_validate({"sources": [spec]}).sources[0]


def _collect(ext, state=None) -> pd.DataFrame:
    frames = [to_text_frame(f) for u in ext.units(state or ExtractState()) for f in u.frames]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


@pytest.mark.parametrize(("lo", "hi", "n"), [(1, 1000, 4), (5, 7, 8), (0, 0, 3), (-10, 10, 3)])
def test_ranges_cover_interval_exactly_once(lo, hi, n):
    ranges = SqlExtractor.ranges(lo, hi, n)
    covered = [v for a, b in ranges for v in range(a, b)]
    assert covered == list(range(lo, hi + 1))


def test_parallel_partitioned_extraction(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'src.db'}"
    with create_engine(url).begin() as c:
        c.execute(text("create table t (id integer, upd integer)"))
        c.execute(text("insert into t values " + ",".join(f"({i},{i})" for i in range(1, 1001))))
    monkeypatch.setenv("SRC_URL", url)
    src = _source(
        {
            "name": "s",
            "kind": "sql",
            "chunk_size": 100,
            "sql": {
                "url_env": "SRC_URL",
                "table": "t",
                "partition": {"column": "id", "num_partitions": 4},
            },
        }
    )
    df = _collect(build_extractor(src, ""))
    assert sorted(int(v) for v in df["id"]) == list(range(1, 1001))

    src_wm = _source(
        {
            "name": "s",
            "kind": "sql",
            "chunk_size": 100,
            "watermark_column": "upd",
            "watermark_type": "integer",
            "sql": {
                "url_env": "SRC_URL",
                "table": "t",
                "partition": {"column": "id", "num_partitions": 3},
            },
        }
    )
    df = _collect(build_extractor(src_wm, ""), ExtractState(watermark=900))
    assert sorted(int(v) for v in df["id"]) == list(range(901, 1001))


def test_parallel_extraction_propagates_errors(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'src.db'}"
    with create_engine(url).begin() as c:
        c.execute(text("create table t (id integer)"))
        c.execute(text("insert into t values (1),(2),(3)"))
    monkeypatch.setenv("SRC_URL", url)
    src = _source(
        {
            "name": "s",
            "kind": "sql",
            "sql": {
                "url_env": "SRC_URL",
                "query": "select id, coluna_inexistente from t",
                "partition": {
                    "column": "id",
                    "num_partitions": 2,
                    "lower_bound": 1,
                    "upper_bound": 3,
                },
            },
        }
    )
    with pytest.raises(Exception, match="coluna_inexistente"):
        _collect(build_extractor(src, ""))


class _Handler(BaseHTTPRequestHandler):
    log: list = []
    tokens_issued = 0
    reject_first = True

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode()
        if self.path == "/token":
            form = parse_qs(raw)
            assert form["grant_type"] == ["client_credentials"]
            assert form["client_id"] == ["cid"] and form["client_secret"] == ["sec"]
            _Handler.tokens_issued += 1
            return self._json(
                200, {"access_token": f"tok{_Handler.tokens_issued}", "expires_in": 3600}
            )
        body = json.loads(raw)
        auth = self.headers.get("Authorization")
        _Handler.log.append({"auth": auth, "variables": body.get("variables")})
        if _Handler.reject_first and auth == "Bearer tok1":
            _Handler.reject_first = False
            return self._json(401, {"error": "expired"})
        if "quebrada" in body["query"]:
            return self._json(200, {"errors": [{"message": "campo inválido"}]})
        after = body["variables"].get("after")
        if after is None:
            page = {
                "nodes": [{"id": 1}, {"id": 2}],
                "pageInfo": {"hasNextPage": True, "endCursor": "c2"},
            }
        else:
            page = {"nodes": [{"id": 3}], "pageInfo": {"hasNextPage": False, "endCursor": None}}
        return self._json(200, {"data": {"pedidos": page}})

    def log_message(self, *args):
        return


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("CID", "cid")
    monkeypatch.setenv("CSEC", "sec")
    _Handler.log, _Handler.tokens_issued, _Handler.reject_first = [], 0, True
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _graphql_source(base: str, query: str = "query($after: String) { pedidos }"):
    return _source(
        {
            "name": "g",
            "kind": "api",
            "chunk_size": 100,
            "api": {
                "url": f"{base}/graphql",
                "records_path": "data.pedidos.nodes",
                "incremental_param": "desde",
                "graphql": {"query": query, "page_info_path": "data.pedidos.pageInfo"},
                "auth": {
                    "type": "oauth2_client_credentials",
                    "token_url": f"{base}/token",
                    "client_id_env": "CID",
                    "client_secret_env": "CSEC",
                },
            },
        }
    )


def test_graphql_cursor_pagination_with_oauth_refresh(server):
    df = _collect(
        build_extractor(_graphql_source(server), ""), ExtractState(watermark="2026-01-01")
    )
    assert df["id"].tolist() == ["1", "2", "3"]
    assert _Handler.tokens_issued == 2
    assert _Handler.log[0]["auth"] == "Bearer tok1"
    assert _Handler.log[-1]["variables"] == {"desde": "2026-01-01", "after": "c2"}


def test_graphql_errors_are_raised(server):
    with pytest.raises(GraphQLError, match="campo inválido"):
        _collect(build_extractor(_graphql_source(server, "query quebrada"), ""))


def test_oauth_requires_all_fields():
    with pytest.raises(Exception, match="token_url"):
        _source(
            {
                "name": "a",
                "kind": "api",
                "api": {"url": "https://x", "auth": {"type": "oauth2_client_credentials"}},
            }
        )
