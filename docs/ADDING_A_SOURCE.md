# Adicionar uma fonte

## 1. Escolha a estratégia

| Pergunta | Resposta → estratégia |
|---|---|
| A origem é pequena e não tem chave/data confiável? | `full` |
| Os registros nunca mudam depois de criados (eventos, logs, fotos)? | `append` |
| Os registros são atualizados (status, valores) e têm chave? | `merge` + `primary_key` |
| Volume muito alto e o PostgreSQL não precisa do dado bruto? | `sink: parquet` + `append` |

## 2. Declare no `config/sources.yml`

### Arquivo
```yaml
- name: pedidos
  kind: file
  owner: comercial@empresa
  description: Pedidos exportados do ERP
  load_strategy: merge
  primary_key: [pedido_id]
  pii_columns: [cliente_email]
  file:
    path: "erp/pedidos_*.csv"   # relativo a DH_LANDING_URI; glob permitido
    format: csv                  # csv | jsonl | json | parquet | xlsx
    sep: ";"
    encoding: latin-1
```

### API REST
```yaml
- name: crm_clientes
  kind: api
  load_strategy: merge
  primary_key: [id]
  watermark_column: updated_at     # nome na origem (aninhado: meta.updated)
  watermark_type: timestamp
  api:
    url: https://api.crm.com/v2/clientes
    auth: { type: bearer, token_env: CRM_TOKEN }   # valor fica no .env
    records_path: data.items
    incremental_param: updated_since
    pagination: { type: cursor, cursor_param: cursor, next_cursor_path: meta.next }
    rate_limit_per_second: 5
```
Paginação: `none | page | offset | cursor | link_header`. Retry exponencial para 429/5xx respeitando `Retry-After`.

### Banco relacional
```yaml
- name: erp_titulos
  kind: sql
  load_strategy: merge
  primary_key: [titulo_id]
  watermark_column: dt_alteracao
  chunk_size: 20000
  sql:
    url_env: ERP_DB_URL     # ex.: oracle+oracledb://user:pass@host:1521/?service_name=ORCL
    query: SELECT * FROM financeiro.titulos
```
Instale o driver: `pip install -e ".[oracle]"` (ou `mssql`, `mysql`). No Docker, adicione o extra ao `Dockerfile`.

## 3. Valide antes de gravar

```bash
python -m datahack_ingest validate                 # schema do catálogo + variáveis de ambiente
python -m datahack_ingest run pedidos --dry-run    # extrai, normaliza e mostra colunas/linhas
python -m datahack_ingest run pedidos              # grava bronze.pedidos
```

Os nomes de coluna viram snake_case ASCII (`Data Emissão` → `data_emissao`, `valorTotal` → `valor_total`).

## 4. Modele a Silver

```sql
-- dbt/models/silver/stg_pedidos.sql
with latest as (
    {{ dh_latest(source('bronze', 'pedidos'), ['pedido_id']) }}
)
select
    {{ dh_to_int('pedido_id') }}                      as pedido_id,
    {{ dh_to_date('data_emissao', 'dmy') }}           as data_emissao,
    {{ dh_to_numeric('valor_total', decimal=',') }}   as valor_total,
    {{ dh_hash_pii('cliente_email') }}                as cliente_hash,
    _dh_ingested_at
from latest
```

Registre a tabela em `dbt/models/bronze/_bronze__sources.yml` e os testes em `_silver__models.yml`
(no mínimo `not_null` + `unique` na chave). Modelo com `dh_hash_pii` deve ser `table`/`incremental`, nunca `view`.

## 5. Publique na Gold

Crie dimensão/fato/mart em `dbt/models/gold/`, com contrato (`contract.enforced`) se o BI for consumir,
e rode `dbt build --select stg_pedidos+`.
