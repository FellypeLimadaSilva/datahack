from __future__ import annotations

import os
import shlex
import sys
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag


def notify_failure(context) -> None:
    from datahack_ingest.airflow_hooks import notify_failure as _notify

    _notify(context)


DH_HOME = os.environ.get("DH_HOME", "/opt/datahack")
PYTHON = os.environ.get("DH_PYTHON", sys.executable)
RETENTION = int(os.environ.get("DH_OPS_RETENTION_DAYS", "90"))


@dag(
    dag_id="warehouse_maintenance",
    schedule="0 3 * * 0",
    start_date=pendulum.datetime(2026, 1, 1, tz=os.environ.get("DH_TIMEZONE", "America/Cuiaba")),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "dba", "retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["dba", "manutencao"],
)
def warehouse_maintenance():
    BashOperator(
        task_id="analyze_and_purge",
        cwd=DH_HOME,
        bash_command=(
            f"{shlex.quote(PYTHON)} -m datahack_ingest maintenance --retention-days {RETENTION}"
        ),
        execution_timeout=timedelta(hours=1),
        on_failure_callback=notify_failure,
    )


warehouse_maintenance()
