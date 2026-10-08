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

### Formatos e compactação

| `format` | Opções específicas |
|---|---|
| `csv` | `sep`, `encoding`, `quotechar`, `skip_rows` |
| `jsonl` / `json` | `records_path` (ex.: `data.items`), `flatten_max_level`; JSON lido em streaming |
| `parquet` / `orc` / `avro` | nenhuma (tipos preservados como texto) |
| `xlsx` | `sheet_name`, `skip_rows`; leitura em streaming |
| `xml` | `record_tag` (elemento que representa uma linha); entidades e DTD bloqueados |
| `fixed_width` | `widths`, `names` |

`compression: infer` (padrão) reconhece `.gz`, `.bz2`, `.xz`, `.zst` e `.zip`; em zip, use
`zip_member_pattern` (ex.: `"*.csv"`).

### Transformações antes de gravar (ETL)
```yaml
  transforms:
    - { op: filter, column: status, operator: in, value: [ativo, suspenso] }
    - { op: hash_columns, columns: [cpf], digits_only: true }
    - { op: mask_columns, columns: [cartao], keep_last: 4 }
    - { op: drop_columns, columns: [senha, token] }
    - { op: python, callable: "meu_pacote.regras:enriquecer" }
```
Os nomes de coluna são os já normalizados (veja no `--dry-run`).

### Exclusões, volume, paralelismo e autenticação
```yaml
  delete_detection: { mode: soft, scope: snapshot, max_delete_ratio: 0.2 }
  volume_check: { min_ratio: 0.5, max_ratio: 3, lookback_runs: 7, min_history: 3, action: fail }
  sql:
    partition: { column: id, num_partitions: 8 }
  api:
    auth:
      type: oauth2_client_credentials
      token_url: https://auth.exemplo.com/oauth/token
      client_id_env: CLIENT_ID
      client_secret_env: CLIENT_SECRET
    graphql:
      query: "query($after: String) { pedidos(after: $after) { nodes { id } pageInfo { hasNextPage endCursor } } }"
      page_info_path: data.pedidos.pageInfo
    records_path: data.pedidos.nodes
```
Exemplos completos e desabilitados estão em `config/sources.yml`.

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
