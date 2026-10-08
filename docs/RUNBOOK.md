# Runbook de operação

## Saúde da plataforma

```bash
docker compose ps                               # todos "healthy"
docker compose logs --tail=100 airflow-scheduler
```

```sql
-- Últimas execuções e falhas
select source, status, started_at, rows_loaded, rows_rejected, duration_s, error
from ops.ingestion_runs order by started_at desc limit 20;

-- Atualização vista pelo BI
select * from gold.controle_atualizacao;

-- Linhas em quarentena
select source, reason, count(*) from ops.rejected_rows group by 1, 2;

-- Colunas novas detectadas (schema drift)
select * from ops.schema_changes order by detected_at desc;
```

## Problemas comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| `port is already allocated` (5433/8080) | Outro PostgreSQL/serviço local | Mude `WAREHOUSE_PORT`/`AIRFLOW_PORT` no `.env` |
| `required variable ... is missing` no compose | `.env` ausente | `python scripts/init_env.py` |
| `10-bootstrap.sh: bad interpreter` | Script salvo com CRLF | `git config core.autocrlf false` e clone de novo (o `.gitattributes` força LF) |
| `SourceLockedError` | Mesma fonte já rodando | Aguarde; se for órfão: `select pg_terminate_backend(pid) from pg_locks where locktype='advisory'` |
| `primary_key ausente nos dados` | Nome da chave diferente após normalização | Rode `--dry-run` e use o nome normalizado |
| `FileNotFoundError ... carga full abortada` | Proteção contra truncar a Bronze sem arquivo | Verifique `file.path` e `DH_LANDING_URI` |
| dbt `contract ... mismatch` | Tipo/coluna mudou em model da Gold | Ajuste o model **e** o `.yml`; avise o consumidor do BI |
| `could not resize shared memory segment` | `/dev/shm` pequeno | Já tratado com `shm_size: 1g`; aumente se necessário |
| Senha trocada no `.env` não vale | Bootstrap roda só no 1º volume | `make db-bootstrap` / `dh.ps1 db-bootstrap` |
| `DeleteGuardError ... exclusão bloqueada` | Snapshot veio incompleto ou a origem apagou mais que `max_delete_ratio` | Confirme com o dono do dado; se for legítimo, aumente `max_delete_ratio` temporariamente |
| `VolumeAnomalyError` | Volume fora da faixa de `volume_check` | Veja `ops.data_quality_events`; arquivo truncado na origem é o caso mais comum |
| `TransformError ... colunas inexistentes` | Transformação usa nome não normalizado | Rode `--dry-run` e use os nomes de `columns` |
| Alertas não chegam | Canal não configurado ou webhook inválido | `dh.ps1 alert-test`; confira `DH_ALERT_*` no `.env` |

## Reprocessamento

```bash
# Reprocessar um arquivo já carregado (remove do manifesto e reingere)
psql ... -c "delete from ops.file_manifest where source='vendas' and file_uri like '%vendas_2026%'"
python -m datahack_ingest run vendas

# Reconstruir incrementais do dbt
dbt build --select stg_vendas+ --full-refresh
```

Pela UI do Airflow: *Trigger DAG w/ config* → `{"sources": ["vendas"], "dbt_select": "stg_vendas+", "full_refresh": true}`.

## Backup e restauração

O serviço `warehouse-backup` gera `backups/<db>_<UTC>.dump` diariamente (`BACKUP_INTERVAL_SECONDS`),
valida cada arquivo com `pg_restore --list`, grava o `.sha256` e apaga os mais antigos que
`BACKUP_RETENTION_DAYS`. Backup imediato: `dh.ps1 backup` / `make backup`.

```bash
docker compose exec -T warehouse bash -c 'createdb -U "$POSTGRES_USER" datahack_restore'
docker compose exec -T warehouse bash -c 'pg_restore -U "$POSTGRES_USER" --no-owner -d datahack_restore' < backups/<arquivo>.dump
```
Restaure em banco novo, valide (contagens da Gold, `gold.controle_atualizacao`) e só então troque.

## Réplica de leitura

`dh.ps1 ha-up` / `make ha-up` cria a réplica em `localhost:5434` com `pg_basebackup` e slot
`replica_1`. Aponte o BI para ela para isolar consultas pesadas do pipeline.

```sql
select application_name, state, sync_state, replay_lag from pg_stat_replication;
```
Para desativar de vez: pare a réplica e remova o slot no primário
(`select pg_drop_replication_slot('replica_1')`), senão o WAL fica retido até `max_slot_wal_keep_size`.

## Alertas

Configure um ou mais canais no `.env` (`DH_ALERT_SLACK_WEBHOOK_URL`, `DH_ALERT_TEAMS_WEBHOOK_URL`,
`DH_ALERT_WEBHOOK_URL`, `DH_SMTP_*` + `DH_ALERT_EMAIL_TO`) e rode `dh.ps1 alert-test`.
Disparam em: falha de ingestão, volume anômalo e falha do `dbt_build`/`list_sources` no Airflow.

## Manutenção

A DAG `warehouse_maintenance` (domingo 03:00) roda `ANALYZE` na Bronze e expurga `ops.*` com mais de 90 dias
(`DH_OPS_RETENTION_DAYS`). Consultas lentas: `select * from pg_stat_statements order by total_exec_time desc limit 20;`.

## Reset total (destrutivo)

```bash
docker compose down -v    # apaga warehouse, metadados do Airflow e logs
```
