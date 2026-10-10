SHELL := /bin/bash
COMPOSE := docker compose
CLI := $(COMPOSE) run --rm cli

.DEFAULT_GOAL := help
.PHONY: help env up up-lite smoke down restart ps logs build sample demo-inbox discover ingest models export dbt-build dbt-test dbt-docs pipeline images-save images-load \
        psql db-bootstrap backup ha-up alert-test test lint fmt clean nuke

help:
	@echo "env build up up-lite smoke down restart ps logs sample demo-inbox discover ingest models export images-save images-load dbt-build dbt-test dbt-docs pipeline psql db-bootstrap backup ha-up alert-test test lint fmt clean nuke"

env:
	python3 scripts/init_env.py

build: env
	$(COMPOSE) build

up: env
	$(COMPOSE) up -d --build
	@echo "Airflow: http://localhost:$${AIRFLOW_PORT:-8080} | Postgres: localhost:$${WAREHOUSE_PORT:-5433}"

up-lite: env
	$(COMPOSE) build cli
	$(COMPOSE) up -d --wait warehouse
	$(CLI) python -m datahack_ingest init

smoke:
	$(CLI) python -m datahack_ingest --version
	$(CLI) python -m datahack_ingest init
	$(CLI) python -m datahack_ingest validate
	$(CLI) dbt debug --project-dir dbt

images-save:
	mkdir -p images
	docker save -o images/datahack-images.tar $$(for i in $$($(COMPOSE) --profile cli config --images | sort -u); do docker image inspect $$i >/dev/null 2>&1 && echo $$i; done)

images-load:
	docker load -i images/datahack-images.tar

down:
	$(COMPOSE) down

restart: down up

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200 $(s)

sample:
	$(CLI) python scripts/generate_sample_data.py --out data/landing/sample

demo-inbox:
	$(CLI) python scripts/generate_messy_data.py --out data/landing/inbox

discover:
	$(CLI) python -m datahack_ingest discover

ingest:
	$(CLI) python -m datahack_ingest run $(if $(s),$(s),--all --continue-on-error)

models:
	$(CLI) python -m datahack_ingest generate-models $(if $(reset),--reset,)

export:
	$(CLI) python -m datahack_ingest export

dbt-build:
	$(CLI) dbt build --project-dir dbt $(if $(sel),--select $(sel),)

dbt-test:
	$(CLI) dbt test --project-dir dbt

dbt-docs:
	$(CLI) bash -c "DBT_TARGET_PATH=/opt/datahack/dbt/target dbt docs generate --project-dir dbt"

pipeline:
	@status=0; $(CLI) python -m datahack_ingest run --all --continue-on-error || status=$$?; \
	if [ $$status -ne 0 ] && [ "$${DH_REQUIRE_ALL_SOURCES:-false}" = "true" ]; then exit $$status; fi; \
	$(CLI) python -m datahack_ingest generate-models && \
	$(CLI) dbt build --project-dir dbt && \
	$(CLI) python -m datahack_ingest export && exit $$status

psql:
	$(COMPOSE) exec warehouse bash -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

backup:
	$(COMPOSE) run --rm -e BACKUP_ONCE=true warehouse-backup

ha-up:
	$(COMPOSE) --profile ha up -d warehouse-replica

alert-test:
	$(CLI) python -m datahack_ingest alert-test

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
