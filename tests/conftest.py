from __future__ import annotations

import os
import uuid

import pytest

from datahack_ingest.settings import Settings


def _pg_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(Settings.from_env().conninfo(), connect_timeout=3):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def settings() -> Settings:
    if not os.environ.get("WAREHOUSE_INGEST_PASSWORD") and not os.path.exists(".env"):
        pytest.skip("warehouse não configurado (WAREHOUSE_*)")
    if not _pg_available():
        pytest.skip("PostgreSQL inacessível")
    return Settings.from_env()


@pytest.fixture
def unique_name() -> str:
    return f"t_{uuid.uuid4().hex[:10]}"
