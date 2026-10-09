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


def _flag(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "sim", "on"}:
        return True
    if lowered in {"0", "false", "no", "nao", "não", "off"}:
        return False
    raise ValueError(f"{name}: valor booleano inválido {value!r}")


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
    examples_enabled: bool = True
    examples_catalog_path: Path = Path("config/examples.yml")
    inbox_enabled: bool = True
    inbox_path: str = "inbox"
    inbox_settle_seconds: int = 15
    dbt_project_dir: Path = Path("dbt")
    auto_models_enabled: bool = True
    auto_type_threshold: float = 0.98
    auto_sample_rows: int = 200_000
    auto_incremental_rows: int = 2_000_000

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
            examples_enabled=_flag("DH_EXAMPLES", True),
            examples_catalog_path=Path(_env("DH_EXAMPLES_CATALOG", "config/examples.yml")),
            inbox_enabled=_flag("DH_INBOX_ENABLED", True),
            inbox_path=_env("DH_INBOX", "inbox"),
            inbox_settle_seconds=int(_env("DH_INBOX_SETTLE_SECONDS", "15")),
            dbt_project_dir=Path(_env("DBT_PROJECT_DIR", "dbt")),
            auto_models_enabled=_flag("DH_AUTO_MODELS", True),
            auto_type_threshold=float(_env("DH_AUTO_TYPE_THRESHOLD", "0.98")),
            auto_sample_rows=int(_env("DH_AUTO_SAMPLE_ROWS", "200000")),
            auto_incremental_rows=int(_env("DH_AUTO_INCREMENTAL_ROWS", "2000000")),
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
