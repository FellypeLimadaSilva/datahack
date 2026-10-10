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
    dbt_project_dir: Path = Path("dbt")
    dbt_target: str = "dev"
    transform_user: str = "dh_transformer"
    transform_password: str | None = field(default=None, repr=False)
    bi_role: str = "dh_bi_reader"
    gold_schema: str = "gold"
    candidate_schema: str = "gold_candidate"
    previous_schema: str = "gold_previous"
    export_config_path: Path = Path("config/exports.yml")
    outputs_dir: Path = Path("outputs")
    export_user: str = "dh_bi_reader"
    export_password: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv_once()
        return cls(
            catalog_path=Path(_env("DH_CATALOG", "config/sources.yml")),
            landing_uri=_env("DH_LANDING_URI", "data/landing"),
            pg_host=_env("WAREHOUSE_HOST", "localhost"),
            pg_port=int(_env("WAREHOUSE_PORT", "5433")),
            pg_db=_env("WAREHOUSE_DB", "datahack"),
            pg_user=_env("WAREHOUSE_INGEST_USER", "dh_ingestor"),
            pg_password=_env("WAREHOUSE_INGEST_PASSWORD"),
            pg_dsn=_env("WAREHOUSE_INGEST_DSN"),
            pg_sslmode=_env("WAREHOUSE_SSLMODE", "prefer"),
            log_format=_env("DH_LOG_FORMAT", "text"),
            log_level=_env("DH_LOG_LEVEL", "INFO"),
            dbt_project_dir=Path(_env("DBT_PROJECT_DIR", "dbt")),
            dbt_target=_env("DBT_TARGET", "dev"),
            transform_user=_env("WAREHOUSE_DBT_USER", "dh_transformer"),
            transform_password=_env("WAREHOUSE_DBT_PASSWORD"),
            bi_role=_env("DBT_BI_ROLE", "dh_bi_reader"),
            export_config_path=Path(_env("DH_EXPORT_CONFIG", "config/exports.yml")),
            outputs_dir=Path(_env("DH_OUTPUTS", "outputs")),
            export_user=_env("WAREHOUSE_EXPORT_USER", _env("WAREHOUSE_BI_USER", "dh_bi_reader")),
            export_password=_env("WAREHOUSE_EXPORT_PASSWORD", _env("WAREHOUSE_BI_PASSWORD")),
        )

    @property
    def dbt_target_path(self) -> Path:
        configured = _env("DBT_TARGET_PATH")
        if not configured:
            return self.dbt_project_dir / "target"
        path = Path(configured)
        return path if path.is_absolute() else self.dbt_project_dir / path

    def transform_conninfo(self) -> str:
        return make_conninfo(
            host=self.pg_host,
            port=self.pg_port,
            dbname=self.pg_db,
            user=self.transform_user,
            password=self.transform_password or None,
            sslmode=self.pg_sslmode,
            application_name="datahack-publish",
            connect_timeout=10,
        )

    def export_conninfo(self) -> str:
        return make_conninfo(
            host=self.pg_host,
            port=self.pg_port,
            dbname=self.pg_db,
            user=self.export_user,
            password=self.export_password or None,
            sslmode=self.pg_sslmode,
            application_name="datahack-export",
            connect_timeout=10,
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
