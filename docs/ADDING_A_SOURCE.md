# Adicionar uma fonte

## 0. Caminho rápido: inbox

Copie para `data/landing/inbox/` e rode `dh.ps1 pipeline` (ou a DAG). Nada a declarar.

| O que você coloca | Vira |
|---|---|
| `inbox/vendas/` com vários arquivos | uma fonte `vendas` (todos os arquivos, inclusive subpastas e compactados) |
| `inbox/Clientes 2026.csv` | uma fonte `clientes` (o ano sai do nome) |
| `inbox/CPC_2021.xlsx`, `inbox/CPC_2022.xlsx` | uma fonte `cpc` com os dois anos |
| `inbox/Estoque.xlsx` com 3 abas | três fontes `estoque_<aba>` |
| `inbox/legado.db` (SQLite) | uma fonte por tabela, `legado_<tabela>` |
| `inbox/censo_2023.zip`, `inbox/censo_2024.zip` | uma fonte por arquivo de dados dentro dos zips (cursos, IES), juntando os anos |
| PDF, imagem, `.xls`, Access, dump SQL, dicionário, leia-me | ignorado, com motivo em `dh.ps1 discover` |

Detectado sozinho: formato pela extensão, compactação, separador (`,` `;` TAB `|`), encoding
(UTF-8, UTF-8 com BOM, UTF-16, Windows-1252), linha do cabeçalho (títulos acima da tabela, como nas
planilhas do INEP), linhas de nota no rodapé do Excel, primeira aba visível, elemento de registro do
XML e lista de registros do JSON. Arquivo modificado há menos de `DH_INBOX_SETTLE_SECONDS` espera a próxima execução.
Arquivos de uma pasta são lidos em ordem alfabética: nomeie séries com data (`2026_01`, `2026_02`)
para a versão mais nova vencer na deduplicação.

Para arquivos soltos, use `inbox/_sources.yml`, com o nome da fonte como chave:

```yaml
microdados_cadastro_cursos:
  transforms:
    - { op: filter, column: sg_uf, operator: eq, value: MT }
```

Ajuste fino por pasta com `_source.yml` (os mesmos campos do catálogo, exceto `kind`):

```yaml
name: pedidos_erp
load_strategy: merge
primary_key: [pedido_id]
pii_columns: [documento]
file:
  format: fixed_width
  widths: [10, 30, 12]
  names: [pedido_id, cliente, valor]
```

Para ver o resultado: `dh.ps1 discover`, depois `dh.ps1 models` e a tabela `gold.dh_catalogo_dados`.

### Como a Silver/Gold automática decide

| Decisão | Regra |
|---|---|
| Tipo | `bigint`, `numeric` (ponto ou vírgula, aceita `R$`), `date` (ISO, dd/mm/aaaa, mm/dd/aaaa), `timestamp`/`timestamptz`, `boolean` (sim/não, true/false), `jsonb`, senão `text`; exige 98% dos valores válidos na amostra (`DH_AUTO_TYPE_THRESHOLD`) |
| Código continua texto | zeros à esquerda, 15+ dígitos, nome como `cpf`, `cnpj`, `cep`, `codigo`, `chave`, `matricula`, ou prefixo `co_`, `cd_`, `tp_`, `id_` (padrão INEP) |
| Chave | `primary_key` declarada; senão `id`, `codigo`, `uuid`, `<tabela>_id`, `cod_<tabela>`, desde que única e não nula em cada arquivo; senão deduplica pelo hash da linha |
| PII pseudonimizada | nome (`cpf`, `email`, `telefone`, `rg`, `cartao`, `pis`, `cns`...), conteúdo (CPF com dígito verificador válido, e-mail, telefone formatado) ou `pii_columns`; vira `<coluna>_hash` |
| Dado pessoal sinalizado | `nome_cliente`, `endereco`, `nascimento`, `cep`...: mantido, marcado como `pessoal` no catálogo |
| Materialização | Silver `table`; `incremental` (merge) a partir de `DH_AUTO_INCREMENTAL_ROWS`; Gold é view sobre a Silver |
| Estabilidade | tipos e chave ficam gravados em `ops.data_catalog`/`ops.auto_models`; só colunas novas são perfiladas. `dh.ps1 models --reset` refaz tudo |

Valor que não cabe no tipo inferido vira nulo na Silver, fica intacto na Bronze, é contado em
`_dh_invalid_columns` e gera aviso no teste `dh_invalid_ratio`.

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
    format: csv                  # csv | jsonl | json | parquet | xlsx | xml | avro | orc
    sep: ";"                     # ou "auto"
    encoding: auto               # padrão; ou utf-8, cp1252, latin-1
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

### Banco relacional (SQLite em arquivo: `url: "sqlite:///caminho.db"` sem segredo)
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
| `csv` | `sep` (ou `auto`), `encoding` (padrão `auto`), `quotechar`, `skip_rows` |
| `jsonl` / `json` | `records_path` (ex.: `data.items`, ou `auto`), `flatten_max_level`; JSON lido em streaming |
| `parquet` / `orc` / `avro` | nenhuma (tipos preservados como texto) |
| `xlsx` | `sheet_name`, `skip_rows`; leitura em streaming |
| `xml` | `record_tag` (omitido = inferido); entidades e DTD bloqueados |
| todos | `path` aceita arquivo, glob ou pasta; `include`/`exclude` (padrões de nome); `min_age_seconds` |
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

## 4. Modele a Silver (quando a automática não basta)

Ao criar um modelo que use `source('bronze', 'pedidos')`, a geração automática dessa tabela para
sozinha na próxima execução.

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

Registre a tabela numa fonte `bronze` (veja `dbt/models/examples/_examples__sources.yml`) e os
testes num `.yml` ao lado do modelo (no mínimo `not_null` + `unique` na chave). Modelo com
`dh_hash_pii` deve ser `table`/`incremental`, nunca `view`.

## 5. Publique na Gold

Crie dimensão/fato/mart em `dbt/models/gold/`, com contrato (`contract.enforced`) se o BI for consumir,
e rode `dbt build --select stg_pedidos+`.
