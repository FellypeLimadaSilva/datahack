# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) · Versionamento: [SemVer](https://semver.org/lang/pt-BR/).

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
