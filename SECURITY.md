# Segurança e LGPD

## Modelo de ameaça (ambiente de evento/desenvolvimento)

| Risco | Controle |
|---|---|
| Vazamento de segredo no Git | `.env` ignorado; `init_env.py` gera segredos aleatórios; hook `forbid-env`; gitleaks no pre-commit e no CI |
| Vazamento de dado pessoal no Git | `data/**`, `*.csv`, `*.parquet`, `*.pbix` ignorados; hook `forbid-data-files` |
| Serviço exposto na rede local/Wi-Fi do evento | Todas as portas publicadas só em `127.0.0.1` |
| BI lendo dado bruto/PII | `dh_bi_reader` só tem `USAGE`/`SELECT` em `gold`, sessão read-only, `statement_timeout` |
| Escalada a partir da ingestão | `dh_ingestor` sem acesso a `silver`/`gold`, sem `CREATEDB`/`CREATEROLE` |
| Container do Airflow com credencial de admin do banco | Compose injeta só as variáveis necessárias (sem `env_file`) |
| Injeção de shell via parâmetros da DAG | `Param` com `pattern` e `shlex.quote` nos comandos |
| Hash de PII revertido por dicionário | Salt secreto (`DBT_PII_SALT`); modelos com PII nunca como `view` |
| Metadados do Airflow misturados ao warehouse | PostgreSQL dedicado (`airflow-db`) em rede separada |

## Antes de levar para HML/PRD

- [ ] TLS no PostgreSQL (`ssl = on`, `WAREHOUSE_SSLMODE=verify-full`) e no Airflow (proxy reverso)
- [ ] Segredos em cofre (Azure Key Vault, AWS Secrets Manager, Vault) em vez de `.env`
- [ ] `pg_hba.conf` restrito por sub-rede; sem `0.0.0.0/0`
- [ ] Backups automatizados com teste de restauração
- [ ] Proteção da branch `main` (PR obrigatório, CI verde, CODEOWNERS)
- [ ] Rotacionar qualquer token/senha que já tenha aparecido em print, log ou chat

## Reportar vulnerabilidade

Abra uma issue **privada** (Security → Report a vulnerability) ou contate o mantenedor diretamente.
Não inclua dados pessoais nem credenciais no relato.
