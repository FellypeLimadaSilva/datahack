# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) · Versionamento: [SemVer](https://semver.org/lang/pt-BR/).

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
