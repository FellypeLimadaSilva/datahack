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

```bash
docker compose exec warehouse pg_dump -U dh_admin -d datahack -Fc -f /tmp/datahack.dump
docker compose cp warehouse:/tmp/datahack.dump ./backup/datahack.dump   # backup/ fora do Git
docker compose exec -T warehouse pg_restore -U dh_admin -d datahack --clean < ./backup/datahack.dump
```

## Manutenção

A DAG `warehouse_maintenance` (domingo 03:00) roda `ANALYZE` na Bronze e expurga `ops.*` com mais de 90 dias
(`DH_OPS_RETENTION_DAYS`). Consultas lentas: `select * from pg_stat_statements order by total_exec_time desc limit 20;`.

## Reset total (destrutivo)

```bash
docker compose down -v    # apaga warehouse, metadados do Airflow e logs
```
