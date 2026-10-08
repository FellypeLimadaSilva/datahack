# Arquitetura

## 1. Princípios

1. **ELT medalhão:** carregar primeiro, fiel à origem; transformar dentro do warehouse, versionado (dbt).
2. **Config over code:** fonte nova = YAML validado, não código novo.
3. **Orquestrador-agnóstico:** toda etapa é uma CLI (`python -m datahack_ingest`, `dbt`). Airflow, CI e terminal executam exatamente o mesmo comando.
4. **Regra de ouro do consumo:** BI lê somente `gold`, com uma role de leitura com timeout.
5. **Auditável por padrão:** toda execução deixa rastro em `ops` (quem, quando, quanto, resultado, `run_id` do Airflow).
6. **Seguro por padrão:** menor privilégio, segredos fora do código, portas só em `127.0.0.1`, dado fora do Git.

## 2. Componentes

| Componente | Responsabilidade | Onde |
|---|---|---|
| Catálogo | Declara fontes, estratégia, chave, watermark, PII, dono | `config/sources.yml` |
| `datahack-ingest` | Extract + Load para Bronze/Lake, controle em `ops` | `src/datahack_ingest/` |
| Warehouse | PostgreSQL 16 tunado para OLAP, roles e schemas | `infra/postgres/` |
| dbt | Silver (limpeza/tipagem/PII), Gold (dimensional), testes, contratos | `dbt/` |
| Airflow 3 | Agenda, paraleliza (`.expand`), faz retry e aplica o gate de qualidade | `airflow/dags/` |
| CI | Lint, segredos, e2e em PostgreSQL real, parse das DAGs, build da imagem | `.github/workflows/ci.yml` |

## 3. Fluxo de uma execução (`medallion_pipeline`)

```mermaid
sequenceDiagram
    participant AF as Airflow
    participant IN as datahack-ingest
    participant OPS as ops.*
    participant BR as bronze.*
    participant DBT as dbt build
    AF->>AF: list_sources (lê o YAML em runtime)
    par uma task por fonte (máx. 4 simultâneas)
        AF->>IN: run <fonte>
        IN->>OPS: lock consultivo + ingestion_runs(status=running)
        loop por unidade (arquivo / execução)
            IN->>BR: BEGIN · COPY · (merge) · manifesto/watermark · COMMIT
        end
        IN->>OPS: status=success|failed + métricas
    end
    AF->>DBT: build (somente se todas as fontes = success)
    DBT->>DBT: silver → testes → gold → testes → ANALYZE + GRANT
```

## 4. Estratégias de carga

| Estratégia | Quando usar | Mecânica | Custo |
|---|---|---|---|
| `full` | Cadastros pequenos, origem sem chave/data | `TRUNCATE` + `COPY` numa transação (atômico para leitores) | Reprocessa tudo |
| `append` | Eventos/logs/fotos imutáveis | `COPY` direto; dedup na Silver por `row_number()` | Mínimo na carga |
| `merge` | Entidades que mudam (pedido, cliente) | `COPY` para temp → `INSERT … ON CONFLICT DO UPDATE` só se `_dh_row_hash` mudou | Índice único na chave |

Incremental por **watermark tipado** (`timestamp | integer | string`) em API e SQL; por **manifesto SHA-256** em arquivos.
No `merge`, o filtro usa `>=` (borda reprocessada com segurança); nos demais, `>`.

## 5. Por que a Bronze é toda `text`

- Nenhuma carga quebra por tipo inesperado na origem (o erro mais comum em evento/hackathon).
- Evolução de schema vira `ALTER TABLE ADD COLUMN … text`, sem migração.
- A tipagem acontece uma vez, na Silver, com `pg_input_is_valid` (PG 16): valor inválido vira `NULL` e é **medido** pelo teste `assert_vendas_sem_perda_de_cast`, em vez de abortar o pipeline.

## 6. Escala: o que suporta e qual o próximo passo

| Faixa | Arquitetura recomendada | O que muda |
|---|---|---|
| até ~100 GB / centenas de milhões de linhas | **Padrão deste repositório** | Nada. COPY em lotes, BRIN em `_dh_ingested_at`, incremental na Silver/Gold |
| 100 GB – 1 TB | PostgreSQL com particionamento declarativo por mês nas fatos | `partition by range (data_venda)`; mais RAM e `work_mem`; réplica de leitura para o BI |
| > 1 TB ou streaming | `sink: parquet` (lake) + engine distribuída | Trocar o adapter dbt (`dbt-databricks`, `dbt-spark`, `dbt-duckdb`, Fabric); os models da Silver/Gold são SQL quase ANSI e as macros isolam o que é específico do PostgreSQL |

A ingestão já é limitada por memória constante (lotes de `chunk_size`), lê de S3/ADLS/GCS via `fsspec`
e escreve Parquet particionado (`ingest_date=`), então o caminho de escala não exige reescrever a extração.

Ponto de atenção conhecido: o hash SHA-256 de arquivo lê o arquivo duas vezes (hash + carga). Em objetos muito grandes no S3,
troque por ETag/versão do objeto.

## 7. Decisões de materialização

| Camada | Materialização | Motivo |
|---|---|---|
| Silver (cadastros) | `view` | Barato, sempre atualizado, sem reprocessamento |
| Silver (`stg_vendas`) | `incremental` (delete+insert, lookback 2 h) | Volume + contém hash de PII (salt não pode ficar em definição de view) |
| Gold dimensões / marts | `table` + índices + `ANALYZE` | Performance de consumo no BI |
| Gold `fact_vendas` | `incremental` com contrato | Escala sem rebuild; interface estável |

## 8. Regras de negócio modeladas (varejo)

- **LY:** `dim_data.data_ano_anterior` (calendário) e `data_mesmo_dia_semana_ano_anterior` (−364 dias, varejo).
- **L4L (venda comparável):** loja aberta durante todo o mês equivalente do ano anterior e ainda aberta no mês (`mart_vendas_mensal_loja.is_comparavel_l4l`).
- **Meta/compromisso:** `stg_metas` converte decimal pt-BR; `atingimento_meta_pct` no mart mensal.
- **Estoque (semiaditivo):** soma entre lojas/produtos; no tempo, só a última foto (`is_ultima_foto_mes`).
- **Feriados:** fixos via seed + móveis via algoritmo da Páscoa (testado contra datas oficiais).
- **Dia da semana:** ISO (`isodow`), independente de configuração de sessão.
- **Última atualização no BI:** `gold.controle_atualizacao` (carga real), nunca `NOW()`/`TODAY()` no DAX.

## 9. Registro de decisões (ADRs)

Veja [docs/adr/](adr/). Toda decisão estrutural nova entra como ADR numerado.
