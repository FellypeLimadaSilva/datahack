# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) · Versionamento: [SemVer](https://semver.org/lang/pt-BR/).

## [0.4.0] — 2026-10-09

### Adicionado
- `dh-ingest export`: Gold para `outputs/` em CSV e Parquet, ordenado e determinístico, com remoção de
  grupos abaixo de `min_cell` (padrão 10), trava de tamanho e `_manifest.json` com hash por arquivo;
  task `export_outputs` na DAG; `config/exports.yml`.
- Cabeçalho automático (`skip_rows: auto`) para CSV e Excel, descarte de linhas de nota
  (`drop_note_rows`), `sheet_name: auto`, `recursive`, `zip_members`.
- Inbox: arquivos soltos agrupados por nome sem ano; zip solto separado por arquivo de dados;
  dicionários e leia-me ignorados; `inbox/_sources.yml` para ajustar arquivos soltos.
- Códigos `co_`, `cd_`, `tp_`, `id_` mantidos como texto; teste `dh_join_coverage`, macros
  `dh_join_rate` e `dh_min_cell`.
- Imagem CLI leve (`infra/cli/Dockerfile`), `dh.ps1 up-lite`, `doctor`, `smoke`, `images-save`,
  `images-load`, modo sem Docker (`DH_RUNNER=native`, `db-bootstrap-native`) e `docs/LAB_SETUP.md`.
- Estrutura do evento: `prompts/`, `outputs/`, `dashboard/` (Streamlit lendo `outputs/`), `sql/`,
  `requirements.txt`, `docs/estrategia.md`; `docs/ARCHITECTURE.md` passa a `docs/arquitetura.md`.
- CI: job do fluxo do laboratório em Docker (up-lite, pipeline e exportação) e build da imagem CLI.

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
