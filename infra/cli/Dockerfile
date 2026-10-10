ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

LABEL org.opencontainers.image.title="datahack-cli" \
      org.opencontainers.image.description="datahack-ingest + dbt-postgres, sem Airflow"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client tini \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 50000 --gid 0 --shell /usr/sbin/nologin datahack

COPY pyproject.toml README.md /opt/datahack-pkg/
COPY src /opt/datahack-pkg/src
RUN pip install --upgrade pip \
 && pip install "/opt/datahack-pkg[dbt]" \
 && rm -rf /opt/datahack-pkg

ENV DH_HOME=/opt/datahack \
    DBT_BIN=dbt \
    DBT_PROJECT_DIR=/opt/datahack/dbt \
    DBT_PROFILES_DIR=/opt/datahack/dbt \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_LOG_PATH=/tmp/dbt/logs \
    DH_CATALOG=/opt/datahack/config/sources.yml \
    DH_EXAMPLES_CATALOG=/opt/datahack/config/examples.yml \
    DH_EXPORT_CONFIG=/opt/datahack/config/exports.yml \
    DH_LANDING_URI=/opt/datahack/data/landing \
    DH_LAKE_URI=/opt/datahack/data/lake \
    DH_OUTPUTS=/opt/datahack/outputs \
    DH_LOG_FORMAT=json \
    PYTHONPATH=/opt/datahack/src

WORKDIR /opt/datahack
USER datahack
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "datahack_ingest", "--help"]
