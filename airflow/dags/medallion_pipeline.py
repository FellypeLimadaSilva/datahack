from __future__ import annotations

import os
import shlex
import sys
from datetime import timedelta

import pendulum
import yaml
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Asset, Param, dag, get_current_context, task


def notify_failure(context) -> None:
    from datahack_ingest.airflow_hooks import notify_failure as _notify

    _notify(context)


DH_HOME = os.environ.get("DH_HOME", "/opt/datahack")
CATALOG = os.environ.get("DH_CATALOG", f"{DH_HOME}/config/sources.yml")
DBT_BIN = os.environ.get("DBT_BIN", "dbt")
DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", f"{DH_HOME}/dbt")
DBT_TARGET = os.environ.get("DBT_TARGET", "prod")
PYTHON = os.environ.get("DH_PYTHON", sys.executable)
SCHEDULE = os.environ.get("DH_PIPELINE_SCHEDULE") or None
INGEST_CONCURRENCY = int(os.environ.get("DH_INGEST_CONCURRENCY", "4"))
LOCAL_TZ = os.environ.get("DH_TIMEZONE", "America/Cuiaba")

GOLD_ASSET = Asset(name="datahack_gold", uri="x-datahack://warehouse/gold")
SAFE_PARAM_PATTERN = r"^[A-Za-z0-9_+@:,.*/ -]*$"

default_args = {
    "owner": "engenharia-dados",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=2),
}


@dag(
    dag_id="medallion_pipeline",
    description="ELT medalhão: ingestão config-driven + dbt build (testes como gate).",
    schedule=SCHEDULE,
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    dagrun_timeout=timedelta(hours=4),
    tags=["elt", "medalhao", "dbt"],
    params={
        "sources": Param(
            [],
            type="array",
            items={"type": "string", "pattern": r"^[a-z][a-z0-9_]*$"},
            description="Fontes a ingerir (vazio = todas as habilitadas).",
        ),
        "dbt_select": Param(
            "",
            type="string",
            pattern=SAFE_PARAM_PATTERN,
            description="Seletor dbt (vazio = projeto todo).",
        ),
        "full_refresh": Param(False, type="boolean", description="Reconstrói incrementais."),
    },
)
def medallion_pipeline():
    @task(on_failure_callback=notify_failure)
    def list_sources() -> list[str]:
        requested = get_current_context()["params"].get("sources") or []
        with open(CATALOG, encoding="utf-8") as fh:
            catalog = yaml.safe_load(fh) or {}
        enabled = [s["name"] for s in catalog.get("sources", []) if s.get("enabled", True)]
        unknown = sorted(set(requested) - set(enabled))
        if unknown:
            raise ValueError(f"fontes inexistentes ou desabilitadas: {unknown}")
        selected = requested or enabled
        if not selected:
            raise ValueError("nenhuma fonte habilitada no catálogo")
        return selected

    @task.bash(
        cwd=DH_HOME,
        max_active_tis_per_dag=INGEST_CONCURRENCY,
        map_index_template="{{ source_name }}",
    )
    def ingest(source: str) -> str:
        get_current_context()["source_name"] = source
        return f"{shlex.quote(PYTHON)} -m datahack_ingest run {shlex.quote(source)}"

    dbt_build = BashOperator(
        task_id="dbt_build",
        cwd=DBT_PROJECT_DIR,
        bash_command=(
            f"{shlex.quote(DBT_BIN)} build --target {shlex.quote(DBT_TARGET)}"
            "{% if params.dbt_select %} --select {{ params.dbt_select }}{% endif %}"
            "{% if params.full_refresh %} --full-refresh{% endif %}"
        ),
        outlets=[GOLD_ASSET],
        retries=1,
        on_failure_callback=notify_failure,
    )

    ingest.expand(source=list_sources()) >> dbt_build


medallion_pipeline()
