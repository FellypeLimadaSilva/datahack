#!/usr/bin/env bash
set -euo pipefail

: "${WAREHOUSE_INGEST_PASSWORD:?defina WAREHOUSE_INGEST_PASSWORD no .env}"
: "${WAREHOUSE_DBT_PASSWORD:?defina WAREHOUSE_DBT_PASSWORD no .env}"
: "${WAREHOUSE_BI_PASSWORD:?defina WAREHOUSE_BI_PASSWORD no .env}"
: "${WAREHOUSE_BACKUP_PASSWORD:?defina WAREHOUSE_BACKUP_PASSWORD no .env}"
: "${WAREHOUSE_REPLICATION_PASSWORD:?defina WAREHOUSE_REPLICATION_PASSWORD no .env}"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v dbname="$POSTGRES_DB" \
  -v ingest_pw="$WAREHOUSE_INGEST_PASSWORD" \
  -v dbt_pw="$WAREHOUSE_DBT_PASSWORD" \
  -v bi_pw="$WAREHOUSE_BI_PASSWORD" \
  -v backup_pw="$WAREHOUSE_BACKUP_PASSWORD" \
  -v repl_pw="$WAREHOUSE_REPLICATION_PASSWORD" \
  -f /opt/datahack/postgres/bootstrap.sql

hba="${PGDATA}/pg_hba.conf"
rule="host replication dh_replicator all scram-sha-256"
if ! grep -qxF "$rule" "$hba"; then
  echo "$rule" >> "$hba"
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT pg_reload_conf()" > /dev/null
fi

echo "[bootstrap] roles, schemas, privilégios e replicação aplicados em ${POSTGRES_DB}"
