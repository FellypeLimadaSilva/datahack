ARG AIRFLOW_VERSION=3.3.2
ARG PYTHON_VERSION=3.12
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION
ARG DBT_CORE_VERSION=1.12.5
ARG DBT_POSTGRES_VERSION=1.11.0

LABEL org.opencontainers.image.title="datahack-runtime" \
      org.opencontainers.image.description="Airflow + datahack-ingest + dbt-postgres"

USER root
RUN python -m venv /opt/venvs/dbt \
 && /opt/venvs/dbt/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venvs/dbt/bin/pip install --no-cache-dir \
      "dbt-core==${DBT_CORE_VERSION}" "dbt-postgres==${DBT_POSTGRES_VERSION}" \
 && ln -s /opt/venvs/dbt/bin/dbt /usr/local/bin/dbt \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow
COPY --chown=airflow:0 pyproject.toml README.md /opt/datahack-pkg/
COPY --chown=airflow:0 src /opt/datahack-pkg/src
RUN pip install --no-cache-dir \
      "apache-airflow==${AIRFLOW_VERSION}" \
      /opt/datahack-pkg \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

ENV DH_HOME=/opt/datahack \
    DBT_BIN=/opt/venvs/dbt/bin/dbt \
    DBT_PROJECT_DIR=/opt/datahack/dbt \
    DBT_PROFILES_DIR=/opt/datahack/dbt \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_LOG_PATH=/tmp/dbt/logs \
    DH_CATALOG=/opt/datahack/config/sources.yml \
    DH_EXAMPLES_CATALOG=/opt/datahack/config/examples.yml \
    DH_LANDING_URI=/opt/datahack/data/landing \
    DH_LAKE_URI=/opt/datahack/data/lake \
    DH_LOG_FORMAT=json \
    PYTHONPATH=/opt/datahack/src

WORKDIR /opt/datahack
