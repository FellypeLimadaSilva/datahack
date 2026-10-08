# ADR 0003 — Etapas como CLI; Airflow apenas orquestra

- **Status:** aceito · **Data:** 2026-10-08

## Decisão
Toda lógica vive na CLI `datahack_ingest` e no dbt. A DAG chama comandos, com mapeamento dinâmico
(`.expand`) por fonte lido do catálogo em runtime.

## Consequências
+ Mesmo comando no terminal, no CI e no Airflow: depuração local fiel à produção.
+ Trocar de orquestrador (Dagster, Prefect, cron, Databricks Workflows) não exige reescrever código.
+ dbt em venv isolado na imagem: sem conflito com as constraints do Airflow.
− Sem XCom rico entre tarefas; métricas ficam em `ops.ingestion_runs` (o que é desejável para auditoria).
