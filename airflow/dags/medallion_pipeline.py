from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import Asset, Param, dag, get_current_context, task
from airflow.task.trigger_rule import TriggerRule

log = logging.getLogger(__name__)


def notify_failure(context) -> None:
    from datahack_ingest.airflow_hooks import notify_failure as _notify

    _notify(context)


DH_HOME = os.environ.get("DH_HOME", "/opt/datahack")
DBT_BIN = os.environ.get("DBT_BIN", "dbt")
DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", f"{DH_HOME}/dbt")
DBT_TARGET = os.environ.get("DBT_TARGET", "prod")
PYTHON = os.environ.get("DH_PYTHON", sys.executable)
SCHEDULE = os.environ.get("DH_PIPELINE_SCHEDULE") or None
INGEST_CONCURRENCY = int(os.environ.get("DH_INGEST_CONCURRENCY", "4"))
LOCAL_TZ = os.environ.get("DH_TIMEZONE", "America/Cuiaba")
REQUIRE_ALL = os.environ.get("DH_REQUIRE_ALL_SOURCES", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "sim",
    "on",
}
CLI_TIMEOUT = int(os.environ.get("DH_CLI_TIMEOUT_SECONDS", "600"))
TASK_RETRIES = int(os.environ.get("DH_TASK_RETRIES", "2"))
RETRY_DELAY = timedelta(seconds=int(os.environ.get("DH_RETRY_DELAY_SECONDS", "120")))

GOLD_ASSET = Asset(name="datahack_gold", uri="x-datahack://warehouse/gold")
SAFE_PARAM_PATTERN = r"^[A-Za-z0-9_+@:,.*/ -]*$"

default_args = {
    "owner": "engenharia-dados",
    "retries": TASK_RETRIES,
    "retry_delay": RETRY_DELAY,
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=2),
}


@dag(
    dag_id="medallion_pipeline",
    description="Medalhão: inbox + catálogo -> Bronze -> Silver/Gold -> dbt build -> outputs/.",
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
    def _cli(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [PYTHON, "-m", "datahack_ingest", *args],
            cwd=DH_HOME,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT,
            check=False,
        )

    @task(on_failure_callback=notify_failure)
    def list_sources() -> list[str]:
        requested = get_current_context()["params"].get("sources") or []
        listed = _cli("list", "--json", "--enabled-only")
        if listed.returncode != 0:
            raise RuntimeError(f"catálogo inválido: {listed.stderr.strip()[-2000:]}")
        enabled = [s["name"] for s in json.loads(listed.stdout)]
        discovered = _cli("discover", "--json")
        if discovered.stdout.strip():
            report = json.loads(discovered.stdout)
            for item in report.get("ignored", []):
                log.warning("inbox ignorou %s: %s", item["path"], item["reason"])
            if report.get("errors"):
                from datahack_ingest.alerting import Alert, send_alert

                send_alert(
                    Alert(
                        title="Inbox com arquivos inválidos",
                        message=json.dumps(report["errors"], ensure_ascii=False)[:3000],
                        severity="error",
                        context={"dag": "medallion_pipeline"},
                    )
                )
                log.error("erros na inbox: %s", report["errors"])
        unknown = sorted(set(requested) - set(enabled))
        if unknown:
            raise ValueError(f"fontes inexistentes ou desabilitadas: {unknown}")
        selected = requested or enabled
        if not selected:
            log.warning(
                "nenhuma fonte habilitada: catálogo vazio, exemplos desligados e inbox vazia"
            )
        return selected

    @task.bash(
        cwd=DH_HOME,
        max_active_tis_per_dag=INGEST_CONCURRENCY,
        map_index_template="{{ source_name }}",
    )
    def ingest(source: str) -> str:
        get_current_context()["source_name"] = source
        return f"{shlex.quote(PYTHON)} -m datahack_ingest run {shlex.quote(source)}"

    generate_models = BashOperator(
        task_id="generate_models",
        cwd=DH_HOME,
        bash_command=f"{shlex.quote(PYTHON)} -m datahack_ingest generate-models",
        trigger_rule=TriggerRule.ALL_SUCCESS
        if REQUIRE_ALL
        else TriggerRule.ALL_DONE_MIN_ONE_SUCCESS,
        retries=min(TASK_RETRIES, 1),
        on_failure_callback=notify_failure,
    )

    ingestion_gate = EmptyOperator(task_id="ingestion_gate", trigger_rule=TriggerRule.ALL_SUCCESS)

    dbt_build = BashOperator(
        task_id="dbt_build",
        cwd=DBT_PROJECT_DIR,
        bash_command=(
            f"{shlex.quote(DBT_BIN)} build --target {shlex.quote(DBT_TARGET)}"
            "{% if params.dbt_select %} --select {{ params.dbt_select }}{% endif %}"
            "{% if params.full_refresh %} --full-refresh{% endif %}"
        ),
        outlets=[GOLD_ASSET],
        retries=min(TASK_RETRIES, 1),
        on_failure_callback=notify_failure,
    )

    export_outputs = BashOperator(
        task_id="export_outputs",
        cwd=DH_HOME,
        bash_command=f"{shlex.quote(PYTHON)} -m datahack_ingest export",
        retries=min(TASK_RETRIES, 1),
        on_failure_callback=notify_failure,
    )

    ingested = ingest.expand(source=list_sources())
    ingested >> generate_models >> dbt_build >> export_outputs
    ingested >> ingestion_gate


medallion_pipeline()
