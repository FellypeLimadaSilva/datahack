#!/usr/bin/env bash
set -euo pipefail

: "${PRIMARY_HOST:?}" "${REPLICATION_PASSWORD:?}"
slot="${REPLICATION_SLOT:-replica_1}"
export PGPASSWORD="$REPLICATION_PASSWORD"

mkdir -p "$PGDATA"
chown -R postgres:postgres "$(dirname "$PGDATA")"
chmod 700 "$PGDATA"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  until pg_isready -q -h "$PRIMARY_HOST" -p 5432; do
    sleep 2
  done
  if ! gosu postgres pg_basebackup -h "$PRIMARY_HOST" -p 5432 -U dh_replicator -D "$PGDATA" \
      -R -X stream -C -S "$slot" --checkpoint=fast; then
    rm -rf "${PGDATA:?}"/*
    gosu postgres pg_basebackup -h "$PRIMARY_HOST" -p 5432 -U dh_replicator -D "$PGDATA" \
      -R -X stream -S "$slot" --checkpoint=fast
  fi
fi

exec gosu postgres postgres -c config_file=/etc/postgresql/postgresql.conf -c hot_standby=on
