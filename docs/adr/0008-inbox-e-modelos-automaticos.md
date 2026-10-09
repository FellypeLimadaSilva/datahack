# ADR 0008 — Inbox sem configuração e Silver/Gold geradas automaticamente

- **Status:** aceito · **Data:** 2026-10-09

## Contexto
No evento, a maior parte das bases chega como arquivos heterogêneos (CSV com `;` e Windows-1252,
Excel com várias abas, JSON aninhado, SQLite). Declarar cada fonte e escrever Silver/Gold à mão
consome o tempo que deveria ir para análise, e os modelos de exemplo acoplados quebravam o
`dbt build` quando não havia dados de varejo.

## Decisão
1. `data/landing/inbox/` é varrida a cada execução: pasta, arquivo solto, aba de Excel e tabela de
   SQLite viram fontes `append` (SQLite `full`). Formato, compactação, separador, encoding, nó do
   XML e lista do JSON são detectados por arquivo. `_source.yml` sobrescreve qualquer campo; o
   catálogo YAML tem precedência de nome.
2. `dh-ingest generate-models` perfila cada tabela Bronze sem modelo escrito à mão e gera Silver
   (tipada, deduplicada, PII com hash) e Gold (view) com testes. A inferência roda em SQL sobre
   amostra, usa as mesmas macros de cast da Silver manual e é gravada em `ops.data_catalog` e
   `ops.auto_models`: depois de decidida, não muda sozinha.
3. Chave só por declaração ou por nome de identificador da própria tabela, validada como única por
   arquivo. Na dúvida, deduplicação pelo hash da linha, que nunca descarta linha distinta.
4. Exemplos de varejo isolados em `config/examples.yml` e `dbt/models/examples/`, desligáveis por
   `DH_EXAMPLES`.
5. Falha de uma fonte não bloqueia a Gold das outras (`all_done_min_one_success`); um gate final
   marca a execução como falha. `DH_REQUIRE_ALL_SOURCES=true` restaura o comportamento estrito.

## Consequências
+ Qualquer arquivo tabular suportado chega à Gold sem código; a plataforma roda só com o que for usado.
+ Tipos estáveis evitam quebra de contrato no BI e de incrementais.
+ Nenhum valor de dado é armazenado no catálogo, apenas metadados (LGPD).
− Modelagem de negócio (dimensões, fatos, regras) continua manual; a Gold automática é uma tabela
  pronta para consumo, não um modelo dimensional.
− Valor fora do tipo inferido vira nulo na Silver (medido e alertado, intacto na Bronze); mudar o
  tipo exige `generate-models --reset`.
− Atualização parcial de linha (arquivo só com algumas colunas) substitui a linha inteira pela mais
  recente; para mesclar colunas, declare `load_strategy: merge` com `primary_key`.
