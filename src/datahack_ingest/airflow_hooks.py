from __future__ import annotations

from typing import Any

from datahack_ingest.alerting import Alert, send_alert


def notify_failure(context: dict[str, Any]) -> list[str]:
    ti = context.get("ti") or context.get("task_instance")
    exception = context.get("exception")
    return send_alert(
        Alert(
            title=f"Falha no Airflow: {getattr(ti, 'dag_id', '?')}.{getattr(ti, 'task_id', '?')}",
            message=str(exception)[:2000] if exception else "tarefa falhou",
            severity="error",
            context={
                "dag_run": context.get("run_id"),
                "try_number": getattr(ti, "try_number", None),
                "map_index": getattr(ti, "map_index", None),
            },
        )
    )
