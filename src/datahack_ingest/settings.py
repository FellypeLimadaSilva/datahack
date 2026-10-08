from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from psycopg.conninfo import make_conninfo


def _load_dotenv_once() -> None:
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    catalog_path: Path
    landing_uri: str
    lake_uri: str
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str | None = field(repr=False)
    pg_dsn: str | None = field(default=None, repr=False)
    pg_sslmode: str = "prefer"
    app_name: str = "datahack-ingest"
    log_format: str = "text"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv_once()
        return cls(
            catalog_path=Path(_env("DH_CATALOG", "config/sources.yml")),
            landing_uri=_env("DH_LANDING_URI", "data/landing"),
            lake_uri=_env("DH_LAKE_URI", "data/lake"),
            pg_host=_env("WAREHOUSE_HOST", "localhost"),
            pg_port=int(_env("WAREHOUSE_PORT", "5433")),
            pg_db=_env("WAREHOUSE_DB", "datahack"),
            pg_user=_env("WAREHOUSE_INGEST_USER", "dh_ingestor"),
            pg_password=_env("WAREHOUSE_INGEST_PASSWORD"),
            pg_dsn=_env("WAREHOUSE_INGEST_DSN"),
            pg_sslmode=_env("WAREHOUSE_SSLMODE", "prefer"),
            log_format=_env("DH_LOG_FORMAT", "text"),
            log_level=_env("DH_LOG_LEVEL", "INFO"),
        )

    def conninfo(self) -> str:
        if self.pg_dsn:
            return self.pg_dsn
        return make_conninfo(
            host=self.pg_host,
            port=self.pg_port,
            dbname=self.pg_db,
            user=self.pg_user,
            password=self.pg_password or None,
            sslmode=self.pg_sslmode,
            application_name=self.app_name,
            connect_timeout=10,
        )
