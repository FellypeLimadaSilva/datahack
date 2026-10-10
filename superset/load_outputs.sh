#!/bin/sh
# Recarrega mart.* a partir dos CSVs de ../outputs/superset (o dashboard roda sem o pipeline nem os dados brutos).
#   sh load_outputs.sh [pasta-origem]
# Idempotente: TRUNCATE + COPY.
set -e
cd "$(dirname "$0")"
IN="${1:-../outputs/superset}"
docker compose exec -T db psql -U rota -d rota -v ON_ERROR_STOP=1 -c "TRUNCATE mart.trajetoria, mart.censo_curso, mart.cpc_curso, mart.licenciatura_curso, mart.oferta_municipio, mart.qualidade_checks"
for t in trajetoria censo_curso cpc_curso licenciatura_curso oferta_municipio qualidade_checks; do
  docker compose exec -T db psql -U rota -d rota -v ON_ERROR_STOP=1 -c "\copy mart.$t FROM STDIN WITH (FORMAT csv, HEADER true)" < "$IN/mart_$t.csv"
  echo "carregado mart_$t.csv"
done
