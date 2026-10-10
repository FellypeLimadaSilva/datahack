#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}"
dump="${1:?uso: restore_check.sh <arquivo.dump>}"
scratch="${RESTORE_DB:-${PGDATABASE}_restore_check}"
bi_role="${BI_ROLE:-dh_bi_reader}"

sha_file="${dump}.sha256"
if [ -f "$sha_file" ]; then
  (cd "$(dirname "$dump")" && sha256sum --check --quiet "$(basename "$sha_file")")
fi

dropdb --if-exists "$scratch"
createdb "$scratch"
trap 'dropdb --if-exists "$scratch"' EXIT
pg_restore --exit-on-error --no-owner --dbname="$scratch" "$dump"

counts() {
  psql -d "$1" -tAF '|' -v ON_ERROR_STOP=1 -c "
    SELECT n.nspname || '.' || c.relname, c.oid
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r' AND n.nspname IN ('ops', 'bronze', 'silver', 'gold')
    ORDER BY 1" | while IFS='|' read -r rel _; do
      printf '%s|%s\n' "$rel" "$(psql -d "$1" -tAc "SELECT count(*) FROM $rel")"
    done
}

diff <(counts "$PGDATABASE") <(counts "$scratch")

missing=$(psql -d "$scratch" -tAc "
  SELECT count(*) FROM pg_tables t
  WHERE t.schemaname = 'gold'
    AND NOT has_table_privilege('$bi_role', format('%I.%I', t.schemaname, t.tablename), 'SELECT')")
if [ "$missing" != "0" ]; then
  echo "[restore] $missing tabelas da gold sem SELECT para $bi_role após restaurar" >&2
  exit 1
fi
tables=$(psql -d "$scratch" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname IN ('ops','bronze','silver','gold')")
echo "[restore] ok: $dump restaurado em banco vazio; $tables tabelas com contagens iguais e permissões da gold preservadas"
