from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from datahack_ingest import __version__
from datahack_ingest.catalog import ApiSource
from datahack_ingest.extractors.base import ExtractState, ExtractUnit, get_path, records_to_frame

log = logging.getLogger(__name__)


class ApiExtractor:
    def __init__(self, source: ApiSource) -> None:
        self.source = source
        self.opts = source.api

    def _session(self) -> requests.Session:
        retry = Retry(
            total=self.opts.max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=True,
        )
        s = requests.Session()
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers.update(
            {"Accept": "application/json", "User-Agent": f"datahack-ingest/{__version__}"}
        )
        s.headers.update(self.opts.headers)
        return s

    def units(self, state: ExtractState) -> Iterator[ExtractUnit]:
        parsed = urlparse(self.opts.url)
        yield ExtractUnit(key=f"api:{parsed.netloc}{parsed.path}", frames=self._frames())

    def _frames(self) -> Iterator[pd.DataFrame]:
        with self._session() as session:
            resp = session.get(
                self.opts.url,
                params=self.opts.params,
                timeout=self.opts.timeout_seconds,
                verify=self.opts.verify_tls,
            )
            resp.raise_for_status()
            payload = resp.json()
        records: Any = get_path(payload, self.opts.records_path)
        if isinstance(records, dict):
            records = [records]
        if not records:
            return
        if not isinstance(records, list):
            raise ValueError(f"{self.source.name}: records_path não aponta para uma lista")
        size = self.source.chunk_size
        for start in range(0, len(records), size):
            yield records_to_frame(records[start : start + size], self.opts.flatten_max_level)
