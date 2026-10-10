#!/bin/sh
set -e
if [ "$DATA_SOURCE" = "planilhas" ]; then
  # Plano B: monta o SQLite a partir das planilhas ANTES do Superset conectar, e segue vigiando as pastas
  python /app/planilhas.py || echo ">> PLANILHAS: nada carregado (veja acima); o dashboard abre vazio até chegar uma planilha"
  python /app/planilhas.py --watch "${PLANILHAS_WATCH_SECONDS:-5}" > /proc/1/fd/1 2>&1 &
fi
superset db upgrade
superset fab create-admin --username admin --firstname Rota --lastname Diploma \
  --email admin@example.com --password "$SUPERSET_ADMIN_PASSWORD" || true
superset init
if [ -f /bundle/rota_do_diploma.zip ]; then
  echo ">> conectando à fonte de dados ($DATA_SOURCE) e importando o dashboard (se ainda não existir)"
  python /app/reimport.py --if-missing || echo ">> IMPORTACAO FALHOU (veja acima)"
fi
exec gunicorn -w "${GUNICORN_WORKERS:-2}" --threads 4 --timeout 180 -b 0.0.0.0:8088 "superset.app:create_app()"
