#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}"
dir="${BACKUP_DIR:-/backups}"
interval="${BACKUP_INTERVAL_SECONDS:-86400}"
retention="${BACKUP_RETENTION_DAYS:-7}"
mkdir -p "$dir"

until pg_isready -q -h "$PGHOST" -d "$PGDATABASE"; do
  sleep 5
done

run_backup() {
  local ts final tmp
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  final="${dir}/${PGDATABASE}_${ts}.dump"
  tmp="${dir}/.${PGDATABASE}_${ts}.partial"
  pg_dump --format=custom --compress=6 --no-owner --file="$tmp"
  pg_restore --list "$tmp" > /dev/null
  mv "$tmp" "$final"
  sha256sum "$final" > "${final}.sha256"
  find "$dir" -maxdepth 1 -name "${PGDATABASE}_*.dump*" -mtime +"$retention" -delete
  echo "[backup] $(date -u +%FT%TZ) ok ${final} $(du -h "$final" | cut -f1)"
}

if [ "${BACKUP_ONCE:-false}" = "true" ]; then
  run_backup
  exit 0
fi

while true; do
  run_backup || echo "[backup] $(date -u +%FT%TZ) FALHOU" >&2
  sleep "$interval"
done
