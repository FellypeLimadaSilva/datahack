#!/bin/sh
# Exporta as tabelas mart.* para CSV (UTF-8) em ../outputs/superset  -> vai para o Git (são pequenas, agregadas).
#   sh export_outputs.sh [pasta-destino]
set -e
cd "$(dirname "$0")"
OUT="${1:-../outputs/superset}"
mkdir -p "$OUT"
for t in trajetoria censo_curso cpc_curso licenciatura_curso oferta_municipio qualidade_checks; do
  docker compose exec -T db psql -U rota -d rota -c "\copy mart.$t TO STDOUT WITH (FORMAT csv, HEADER true)" > "$OUT/mart_$t.csv"
  echo "mart_$t.csv  $(($(wc -l < "$OUT/mart_$t.csv") - 1)) linhas"
done
