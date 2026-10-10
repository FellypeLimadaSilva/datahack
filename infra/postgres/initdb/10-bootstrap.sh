#!/usr/bin/env bash
set -euo pipefail

: "${WAREHOUSE_INGEST_PASSWORD:?defina WAREHOUSE_INGEST_PASSWORD no .env}"
: "${WAREHOUSE_DBT_PASSWORD:?defina WAREHOUSE_DBT_PASSWORD no .env}"
: "${WAREHOUSE_BI_PASSWORD:?defina WAREHOUSE_BI_PASSWORD no .env}"
: "${WAREHOUSE_BACKUP_PASSWORD:?defina WAREHOUSE_BACKUP_PASSWORD no .env}"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v dbname="$POSTGRES_DB" \
  -v ingest_pw="$WAREHOUSE_INGEST_PASSWORD" \
  -v dbt_pw="$WAREHOUSE_DBT_PASSWORD" \
  -v bi_pw="$WAREHOUSE_BI_PASSWORD" \
  -v backup_pw="$WAREHOUSE_BACKUP_PASSWORD" \
  -f /opt/datahack/postgres/bootstrap.sql

echo "[bootstrap] roles, schemas e privilégios aplicados em ${POSTGRES_DB}"
