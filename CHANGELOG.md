# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) · Versionamento: [SemVer](https://semver.org/lang/pt-BR/).

## [0.3.0] — 2026-10-09

### Adicionado
- Inbox sem configuração (`data/landing/inbox/`): pasta, arquivo, aba de Excel e tabela de SQLite
  viram fonte; formato, compactação, separador, encoding, nó XML e lista JSON detectados por arquivo;
  `_source.yml` por pasta; arquivos não tabulares ignorados com motivo; espera de estabilização.
- `dh-ingest discover` e `dh-ingest generate-models [--reset]`: Silver e Gold automáticas com tipos
  inferidos (decimal com vírgula, `R$`, dd/mm/aaaa, fuso, booleano pt-BR, `jsonb`), chave validada
  por arquivo, deduplicação, PII pseudonimizada (CPF com dígito verificador, e-mail, telefone),
  testes gerados, `_dh_invalid_columns` e Silver incremental para tabelas grandes.
- `ops.data_catalog`, `ops.auto_models` e `gold.dh_catalogo_dados` (classificação LGPD por coluna).
- Leitura de SQLite com URL literal; `path` aceita pasta com `include`/`exclude`; `encoding: auto`.
- `scripts/generate_messy_data.py` e `dh.ps1 demo-inbox` para demonstrar a inbox.
- `init_env.py` acrescenta variáveis novas a um `.env` existente sem tocar nos segredos.

### Alterado
- Exemplos de varejo isolados em `config/examples.yml` e `dbt/models/examples/` (`DH_EXAMPLES`).
- DAG: `generate_models` entre ingestão e dbt; uma fonte com falha não impede a Gold das demais e
  o `ingestion_gate` marca a execução como falha (`DH_REQUIRE_ALL_SOURCES`, `DH_TASK_RETRIES`).
- `dh.ps1 pipeline` / `make pipeline`: ingestão continua em caso de erro, gera modelos e roda o dbt.
- Macros de cast aceitam `R$`, espaços, `d/m/aaaa` com `/ . -`, `mm/dd/aaaa` e timestamp dd/mm.

## [0.2.0] — 2026-10-08

### Adicionado
- ETL opcional na ingestão: `filter`, `hash_columns`, `mask_columns`, `drop_columns`, `select_columns`,
  `rename`, `deduplicate`, `trim`/`upper`/`lower`, `add_constant` e `python`.
- Detecção de exclusões (`snapshot` e `keys_query`, modos `soft` e `hard`) com trava `max_delete_ratio`,
  propagada para Silver (`dh_latest`) e Gold (`fact_vendas.is_excluida`).
- SCD tipo 2: `snap_lojas`, `snap_produtos`, `dim_loja_historico`, `dim_produto_historico`.
- Formatos XML, largura fixa, Avro e ORC; compactação gzip, bz2, xz, zstd e zip; Excel e JSON em streaming.
- Extração SQL paralela por faixa de chave; OAuth2 client credentials com renovação; GraphQL com cursor.
- Alertas (Slack, Teams, webhook, e-mail), `dh-ingest alert-test`, callbacks no Airflow.
- `volume_check` com eventos em `ops.data_quality_events`.
- Backup automático verificado (`warehouse-backup`) e réplica de leitura (`--profile ha`).
- Roles `dh_backup` e `dh_replicator`; migração automática de `_dh_deleted_at` nas tabelas Bronze.

## [0.1.0] — 2026-10-08

### Adicionado
- Framework de ingestão `datahack-ingest`: arquivos (CSV/JSON/JSONL/Parquet/XLSX via fsspec), APIs REST
  (paginação, auth, retry, incremental) e bancos (SQLAlchemy, cursor no servidor); estratégias full/append/merge;
  manifesto SHA-256, watermark tipado, schema drift, quarentena, lock consultivo; sinks PostgreSQL e Parquet.
- Warehouse PostgreSQL 16 com perfil analítico, roles de menor privilégio e schemas bronze/ops/silver/gold.
- Projeto dbt: 5 models Silver, 3 dimensões, 2 fatos, 2 marts, controle de atualização, 40 testes,
  contratos na Gold, feriados nacionais com Páscoa calculada, L4L/LY/meta.
- Airflow 3.3 (LocalExecutor) com DAG dinâmica `medallion_pipeline` e `warehouse_maintenance`.
- Docker Compose com healthchecks, redes segregadas, portas em 127.0.0.1; devcontainer; tasks do VS Code.
- CI: lint, gitleaks, e2e em PostgreSQL real, parse das DAGs, build da imagem.
- Dataset sintético de varejo (500 mil itens) para demonstração ponta a ponta.
