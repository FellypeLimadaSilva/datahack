# Runbook de operação

## Estado da plataforma

```sql
-- Versão publicada e decisões recentes (aprovadas e rejeitadas, com motivo)
select version, status, published_at, previous, reason from ops.publications order by published_at desc limit 10;

-- Últimas ingestões
select source, status, started_at, rows_loaded, units_processed, units_skipped, error
from ops.ingestion_runs order by started_at desc limit 20;

-- Arquivos carregados por fonte
select source, file_uri, rows_loaded, loaded_at from ops.file_manifest order by source, file_uri;

-- Colunas novas detectadas nos arquivos (schema drift)
select * from ops.schema_changes order by detected_at desc;
```

## Publicação rejeitada

1. `.\scripts\dh.ps1 pipeline` imprime o JSON com `checks`; o primeiro portão reprovado diz o motivo.
2. `fontes`: fonte obrigatória falhou, está vazia ou perdeu coluna essencial. Corrija o arquivo e
   rode de novo (o arquivo com falha foi revertido e não consta no manifesto).
3. `dbt`: rode `.\scripts\dh.ps1 dbt-build` e leia o teste reprovado. Um arquivo corrigido da mesma
   partição (ano, coorte ou edição) substitui o anterior na Silver.
4. Enquanto isso, a Gold e `outputs/` continuam na última versão aprovada.

## Voltar uma versão

`.\scripts\dh.ps1 rollback` troca `gold` e `gold_previous` numa transação e depois
`.\scripts\dh.ps1 export` regrava `outputs/` a partir da versão restaurada.

## Problemas comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| `port is already allocated` (5433/8080) | Outro serviço local | Mude `WAREHOUSE_PORT`/`AIRFLOW_PORT` no `.env` |
| `required variable ... is missing` no compose | `.env` ausente | `.\scripts\dh.ps1 env` |
| `10-bootstrap.sh: bad interpreter` | Script salvo com CRLF | `git config --global core.autocrlf false` e clone de novo |
| `SourceLockedError` | Mesma fonte já rodando | Aguarde; se for órfão: `select pg_terminate_backend(pid) from pg_locks where locktype='advisory'` |
| `sem colunas essenciais` | INEP mudou o nome de uma coluna | Ajuste `essential_columns` e o `stg_*` correspondente |
| `bronze.enade_licenciaturas sem coluna de curso ou de proficiência` | Layout do Enade 2025 diferente do previsto | Veja os nomes em `bronze.enade_licenciaturas` e ajuste os padrões em `stg_enade_licenciaturas.sql` |
| `carga full sem linhas` | API do IBGE fora do ar ou sem internet | Rode depois; a versão anterior foi mantida |
| `could not resize shared memory segment` | `/dev/shm` pequeno | Já tratado com `shm_size: 1g` |

## Backup e restauração

`warehouse-backup` gera um `pg_dump` por dia em `backups/` com `.sha256`. Para provar que o backup
recupera o banco (não basta `pg_restore --list`, que só lê o índice do arquivo):

```bash
PGHOST=localhost PGPORT=5433 PGUSER=dh_admin PGPASSWORD=... PGDATABASE=datahack \
  bash infra/postgres/restore_check.sh backups/datahack_<data>.dump
```

O script restaura num banco vazio, compara a contagem de linhas de todas as tabelas e confere a
permissão de leitura da Gold; termina com erro se algo divergir.
