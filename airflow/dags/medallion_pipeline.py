from __future__ import annotations

import os
import shlex
import sys
from datetime import timedelta
from pathlib import Path

import pendulum
import yaml
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Asset, dag
from airflow.task.trigger_rule import TriggerRule

DH_HOME = os.environ.get("DH_HOME", "/opt/datahack")
CATALOG = Path(os.environ.get("DH_CATALOG", f"{DH_HOME}/config/sources.yml"))
PYTHON = shlex.quote(os.environ.get("DH_PYTHON", sys.executable))
SCHEDULE = os.environ.get("DH_PIPELINE_SCHEDULE") or None
INGEST_CONCURRENCY = int(os.environ.get("DH_INGEST_CONCURRENCY", "4"))
LOCAL_TZ = os.environ.get("DH_TIMEZONE", "America/Cuiaba")
TASK_RETRIES = int(os.environ.get("DH_TASK_RETRIES", "2"))
RETRY_DELAY = timedelta(seconds=int(os.environ.get("DH_RETRY_DELAY_SECONDS", "120")))

GOLD_ASSET = Asset(name="datahack_gold", uri="x-datahack://warehouse/gold")


def enabled_sources(path: Path) -> list[str]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [s["name"] for s in raw.get("sources") or [] if s.get("enabled", True)]


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
    description=(
        "Rota do Diploma: fontes -> Bronze -> portão -> dbt em gold_candidate -> publicação "
        "atômica -> outputs/."
    ),
    schedule=SCHEDULE,
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=INGEST_CONCURRENCY,
    default_args=default_args,
    tags=["elt", "inep", "ibge", "dbt"],
    doc_md=(
        "Cada fonte é ingerida em uma tarefa própria (retries independentes). A tarefa "
        "`publicar` roda mesmo com falhas: ela aplica o portão das fontes obrigatórias, executa "
        "o dbt no schema candidato e só troca a Gold se tudo passar; caso contrário registra a "
        "rejeição em ops.publications e a versão publicada anterior continua valendo."
    ),
)
def medallion_pipeline():
    ingest = [
        BashOperator(
            task_id=f"ingerir__{name}",
            cwd=DH_HOME,
            bash_command=f"{PYTHON} -m datahack_ingest run {shlex.quote(name)}",
        )
        for name in enabled_sources(CATALOG)
    ]
    publicar = BashOperator(
        task_id="publicar",
        cwd=DH_HOME,
        bash_command=(
            f'{PYTHON} -m datahack_ingest pipeline --skip-ingest --orchestrator-run-id "$DH_RUN_ID"'
        ),
        env={"DH_RUN_ID": "{{ run_id }}"},
        append_env=True,
        trigger_rule=TriggerRule.ALL_DONE,
        retries=0,
        outlets=[GOLD_ASSET],
    )
    ingest >> publicar


medallion_pipeline()
