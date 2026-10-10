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
| `password authentication failed for user "dh_bi_reader"` (pgAdmin, Superset) | Senha copiada com o nome da variável ou espaço | `((Get-Content .env \| Select-String '^WAREHOUSE_BI_PASSWORD=').Line -split '=', 2)[1].Trim() \| Set-Clipboard` e cole; host `127.0.0.1`, porta `5433` |
| Superset mostra "Metadados" nos cards e filtros | É a tradução de "No data": o dataset aponta para outro banco ou schema | Em Datasets, Database `datahack` e Schema `gold`; depois Refresh dashboard. Conferência: B1 = 101 municípios sem oferta |
| Números do Superset diferentes dos de `outputs/` | Superset importou outra carga | Reimporte da `main` (`FORCE_REIMPORT=1` no deploy); B1 = 141 municípios, 20,57 vagas por 100 jovens |
| `localhost:8501` recusa conexão | Dashboard ainda instalando ou interrompido com Ctrl+C | Rode `dashboard` e espere "You can now view your Streamlit app" (1 a 2 minutos na primeira vez) |
| Consulta do `diagnostico.sql` volta vazia no PowerShell | `Get-Content` troca a codificação dos acentos | O arquivo usa só códigos e ASCII nos filtros; mantenha assim em novas consultas |
| `dbt debug` falha com `git [ERROR]` na imagem CLI | A imagem não tem git | Use `dbt debug --connection` |

## Backup e restauração

`warehouse-backup` gera um `pg_dump` por dia em `backups/` com `.sha256`. Para provar que o backup
recupera o banco (não basta `pg_restore --list`, que só lê o índice do arquivo):

```bash
PGHOST=localhost PGPORT=5433 PGUSER=dh_admin PGPASSWORD=... PGDATABASE=datahack \
  bash infra/postgres/restore_check.sh backups/datahack_<data>.dump
```

O script restaura num banco vazio, compara a contagem de linhas de todas as tabelas e confere a
permissão de leitura da Gold; termina com erro se algo divergir.
