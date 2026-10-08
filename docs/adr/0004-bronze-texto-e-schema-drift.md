# ADR 0004 — Bronze 100% texto com evolução automática de schema

- **Status:** aceito · **Data:** 2026-10-08

## Decisão
Colunas de negócio gravadas como `text`; coluna nova vira `ALTER TABLE ADD COLUMN` e é registrada em
`ops.schema_changes`. Tipagem na Silver com cast seguro (`pg_input_is_valid`).

## Alternativas consideradas
- *Tipar na ingestão:* quebra a carga a cada valor inesperado.
- *JSONB por linha:* flexível, mas pior para COPY, índices e leitura pelo dbt.

## Consequências
+ Carga nunca falha por tipo; perda de cast é medida por teste, não silenciosa.
− Bronze ocupa mais espaço que tipos nativos (aceitável; é a camada de recuperação).
