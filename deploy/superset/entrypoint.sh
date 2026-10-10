#!/bin/sh
# 1) garante roles/schema e carrega a gold (outputs/*.parquet) no Postgres da Railway; 2) sobe o Superset (init.sh do projeto).
set -e
python /app/load_gold.py
exec sh /app/init.sh
