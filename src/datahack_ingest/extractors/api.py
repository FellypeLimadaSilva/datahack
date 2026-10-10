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

from datahack_ingest.catalog import ApiAuth, ApiSource
from datahack_ingest.extractors.base import ExtractState, ExtractUnit, get_path, records_to_frame

log = logging.getLogger(__name__)
_TOKEN_SKEW_SECONDS = 60


def _secret(name: str | None) -> str:
    if not name:
        raise ValueError("variável de ambiente do segredo não configurada no catálogo")
    value = os.environ.get(name)
    if not value:
        raise OSError(f"variável de ambiente obrigatória ausente: {name}")
    return value


class GraphQLError(RuntimeError):
    pass


class OAuth2ClientCredentials(requests.auth.AuthBase):
    def __init__(self, cfg: ApiAuth, timeout: float, verify: bool) -> None:
        self.cfg = cfg
        self.timeout = timeout
        self.verify = verify
        self._token: str | None = None
        self._expires_at = 0.0

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token and time.monotonic() < self._expires_at - _TOKEN_SKEW_SECONDS:
            return self._token
        data = {"grant_type": "client_credentials"}
        if self.cfg.scope:
            data["scope"] = self.cfg.scope
        if self.cfg.audience:
            data["audience"] = self.cfg.audience
        client_id, client_secret = (
            _secret(self.cfg.client_id_env),
            _secret(self.cfg.client_secret_env),
        )
        auth = None
        if self.cfg.client_auth == "basic":
            auth = (client_id, client_secret)
        else:
            data.update({"client_id": client_id, "client_secret": client_secret})
        resp = requests.post(
            self.cfg.token_url, data=data, auth=auth, timeout=self.timeout, verify=self.verify
        )
        resp.raise_for_status()
        payload = resp.json()
        if "access_token" not in payload:
            raise OSError("resposta do token_url sem access_token")
        self._token = payload["access_token"]
        self._expires_at = time.monotonic() + float(payload.get("expires_in", 3600))
        return self._token

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self.token()}"
        return r


class ApiExtractor:
    def __init__(self, source: ApiSource) -> None:
        self.source = source
        self.opts = source.api
        self._oauth: OAuth2ClientCredentials | None = None

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
        s.headers.update({"Accept": "application/json", "User-Agent": "datahack-ingest/0.2"})
        s.headers.update(self.opts.headers)
        auth = self.opts.auth
        if auth.type == "bearer":
            s.headers["Authorization"] = f"Bearer {_secret(auth.token_env)}"
        elif auth.type == "header":
            s.headers[auth.header] = _secret(auth.token_env)
        elif auth.type == "basic":
            s.auth = (_secret(auth.username_env), _secret(auth.password_env))
        elif auth.type == "oauth2_client_credentials":
            self._oauth = OAuth2ClientCredentials(
                auth, self.opts.timeout_seconds, self.opts.verify_tls
            )
            s.auth = self._oauth
        return s

    def units(self, state: ExtractState) -> Iterator[ExtractUnit]:
        parsed = urlparse(self.opts.url)
        yield ExtractUnit(key=f"api:{parsed.netloc}{parsed.path}", frames=self._frames(state))

    def _frames(self, state: ExtractState) -> Iterator[pd.DataFrame]:
        pages = self._graphql_pages(state) if self.opts.graphql else self._rest_pages(state)
        buffer: list[Any] = []
        for page in pages:
            buffer.extend(page)
            while len(buffer) >= self.source.chunk_size:
                chunk, buffer = buffer[: self.source.chunk_size], buffer[self.source.chunk_size :]
                yield records_to_frame(chunk, self.opts.flatten_max_level)
        if buffer:
            yield records_to_frame(buffer, self.opts.flatten_max_level)

    def _request(
        self,
        session: requests.Session,
        method: str,
        url: str,
        params: dict | None = None,
        body: Any = None,
    ) -> requests.Response:
        if self.opts.rate_limit_per_second:
            time.sleep(1.0 / self.opts.rate_limit_per_second)
        kwargs = {
            "params": params,
            "json": body,
            "timeout": self.opts.timeout_seconds,
            "verify": self.opts.verify_tls,
        }
        resp = session.request(method, url, **kwargs)
        if resp.status_code == 401 and self._oauth:
            self._oauth.invalidate()
            resp = session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    @staticmethod
    def _as_records(value: Any) -> list[Any]:
        if isinstance(value, dict):
            return [value]
        return value or []

    def _graphql_pages(self, state: ExtractState) -> Iterator[list[Any]]:
        gql = self.opts.graphql
        variables: dict[str, Any] = dict(gql.variables)
        with self._session() as session:
            for _ in range(self.opts.pagination.max_pages):
                payload = self._request(
                    session,
                    "POST",
                    self.opts.url,
                    body={"query": gql.query, "variables": variables},
                ).json()
                if payload.get("errors"):
                    raise GraphQLError(str(payload["errors"])[:2000])
                records = self._as_records(get_path(payload, self.opts.records_path))
                if records:
                    yield records
                info = get_path(payload, gql.page_info_path) if gql.page_info_path else None
                if not info or not info.get("hasNextPage") or not info.get("endCursor"):
                    return
                variables[gql.cursor_variable] = info["endCursor"]
            log.warning("max_pages atingido no GraphQL; extração interrompida")

    def _rest_pages(self, state: ExtractState) -> Iterator[list[Any]]:
        p = self.opts.pagination
        params: dict[str, Any] = dict(self.opts.params)
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

                resp = self._request(session, self.opts.method, url, q, self.opts.body)
                payload = resp.json()
                records = self._as_records(get_path(payload, self.opts.records_path))
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
