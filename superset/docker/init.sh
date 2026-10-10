#!/bin/sh
set -e
superset db upgrade
superset fab create-admin --username admin --firstname Rota --lastname Diploma \
  --email admin@example.com --password "$SUPERSET_ADMIN_PASSWORD" || true
superset init
if [ -f /bundle/rota_do_diploma.zip ]; then
  echo ">> conectando ao warehouse e importando o dashboard (se ainda não existir)"
  python /app/reimport.py --if-missing || echo ">> IMPORTACAO FALHOU (veja acima)"
fi
exec gunicorn -w 2 --threads 4 --timeout 180 -b 0.0.0.0:8088 "superset.app:create_app()"
