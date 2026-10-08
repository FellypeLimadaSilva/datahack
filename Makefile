SHELL := /bin/bash
COMPOSE := docker compose
CLI := $(COMPOSE) run --rm cli

.DEFAULT_GOAL := help
.PHONY: help env up down restart ps logs build sample ingest dbt-build dbt-test dbt-docs pipeline \
        psql db-bootstrap test lint fmt clean nuke

help:
	@echo "env build up down restart ps logs sample ingest dbt-build dbt-test dbt-docs pipeline psql db-bootstrap test lint fmt clean nuke"

env:
	python3 scripts/init_env.py

build: env
	$(COMPOSE) build

up: env
	$(COMPOSE) up -d --build
	@echo "Airflow: http://localhost:$${AIRFLOW_PORT:-8080} | Postgres: localhost:$${WAREHOUSE_PORT:-5433}"

down:
	$(COMPOSE) down

restart: down up

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200 $(s)

sample:
	$(CLI) python scripts/generate_sample_data.py --out data/landing/sample

ingest:
	$(CLI) python -m datahack_ingest run $(if $(s),$(s),--all)

dbt-build:
	$(CLI) dbt build --project-dir dbt $(if $(sel),--select $(sel),)

dbt-test:
	$(CLI) dbt test --project-dir dbt

dbt-docs:
	$(CLI) bash -c "DBT_TARGET_PATH=/opt/datahack/dbt/target dbt docs generate --project-dir dbt"

pipeline: ingest dbt-build

psql:
	$(COMPOSE) exec warehouse bash -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

db-bootstrap:
	$(COMPOSE) exec warehouse bash /docker-entrypoint-initdb.d/10-bootstrap.sh

test:
	pytest -q

lint:
	ruff check . && ruff format --check . && sqlfluff lint dbt/models

fmt:
	ruff format . && ruff check --fix .

clean:
	rm -rf .pytest_cache .ruff_cache dbt/target dbt/logs

nuke:
	@read -p "Apagar TODOS os volumes? [digite sim] " ans && [ "$$ans" = "sim" ]
	$(COMPOSE) down -v
