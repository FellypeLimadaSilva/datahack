from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from datahack_ingest.catalog import ApiSource
from datahack_ingest.extractors.base import ExtractState, ExtractUnit, get_path, records_to_frame
from datahack_ingest.normalize import to_text

log = logging.getLogger(__name__)


def _secret(name: str | None) -> str:
    if not name:
        raise ValueError("variável de ambiente do segredo não configurada no catálogo")
    value = os.environ.get(name)
    if not value:
        raise OSError(f"variável de ambiente obrigatória ausente: {name}")
    return value


class ApiExtractor:
    def __init__(self, source: ApiSource) -> None:
        self.source = source
        self.opts = source.api

    def _session(self) -> requests.Session:
        retry = Retry(
            total=self.opts.max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=True,
        )
        s = requests.Session()
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers.update({"Accept": "application/json", "User-Agent": "datahack-ingest/0.1"})
        s.headers.update(self.opts.headers)
        auth = self.opts.auth
        if auth.type == "bearer":
            s.headers["Authorization"] = f"Bearer {_secret(auth.token_env)}"
        elif auth.type == "header":
            s.headers[auth.header] = _secret(auth.token_env)
        elif auth.type == "basic":
            s.auth = (_secret(auth.username_env), _secret(auth.password_env))
        return s

    def units(self, state: ExtractState) -> Iterator[ExtractUnit]:
        host = urlparse(self.opts.url).netloc
        yield ExtractUnit(
            key=f"api:{host}{urlparse(self.opts.url).path}", frames=self._frames(state)
        )

    def _frames(self, state: ExtractState) -> Iterator[pd.DataFrame]:
        buffer: list[Any] = []
        for page in self._pages(state):
            buffer.extend(page)
            while len(buffer) >= self.source.chunk_size:
                chunk, buffer = buffer[: self.source.chunk_size], buffer[self.source.chunk_size :]
                yield records_to_frame(chunk, self.opts.flatten_max_level)
        if buffer:
            yield records_to_frame(buffer, self.opts.flatten_max_level)

    def _request(self, session: requests.Session, url: str, params: dict) -> requests.Response:
        if self.opts.rate_limit_per_second:
            time.sleep(1.0 / self.opts.rate_limit_per_second)
        resp = session.request(
            self.opts.method,
            url,
            params=params,
            json=self.opts.body,
            timeout=self.opts.timeout_seconds,
            verify=self.opts.verify_tls,
        )
        resp.raise_for_status()
        return resp

    def _pages(self, state: ExtractState) -> Iterator[list[Any]]:
        p = self.opts.pagination
        params: dict[str, Any] = dict(self.opts.params)
        if self.opts.incremental_param and state.watermark is not None:
            params[self.opts.incremental_param] = to_text(state.watermark)
        url = self.opts.url
        page, offset, cursor = p.start_page, 0, None

        with self._session() as session:
            for n in range(p.max_pages):
                q = dict(params)
                if p.type == "page":
                    q.update({p.page_param: page, p.size_param: p.page_size})
                elif p.type == "offset":
                    q.update({p.offset_param: offset, p.limit_param: p.page_size})
                elif p.type == "cursor" and cursor:
                    q[p.cursor_param] = cursor

                resp = self._request(session, url, q)
                payload = resp.json()
                records = get_path(payload, self.opts.records_path)
                if isinstance(records, dict):
                    records = [records]
                records = records or []
                log.debug("página recebida", extra={"page": n, "records": len(records)})
                if records:
                    yield records

                if p.type == "none" or not records:
                    return
                if p.type == "page":
                    if len(records) < p.page_size:
                        return
                    page += 1
                elif p.type == "offset":
                    if len(records) < p.page_size:
                        return
                    offset += len(records)
                elif p.type == "cursor":
                    cursor = get_path(payload, p.next_cursor_path)
                    if not cursor:
                        return
                elif p.type == "link_header":
                    nxt = resp.links.get("next", {}).get("url")
                    if not nxt:
                        return
                    url, params = nxt, {}
            log.warning(
                "max_pages atingido; extração interrompida", extra={"max_pages": p.max_pages}
            )
