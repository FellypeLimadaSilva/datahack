# ADR 0006 — ETL opcional na ingestão, ELT como padrão

- **Status:** aceito · **Data:** 2026-10-08

## Contexto
Alguns dados não podem chegar ao banco (LGPD, minimização), outros chegam com ruído demais para valer a gravação.

## Decisão
Manter ELT como padrão e permitir `transforms` declarativas por fonte, executadas por lote antes da gravação.
Hash de PII usa o mesmo algoritmo e salt do dbt, para que chaves pseudonimizadas na ingestão e na Silver coincidam.

## Consequências
+ LGPD por minimização na origem sem sair do framework.
+ Regra própria via `python: modulo:funcao` sem alterar o núcleo.
− Dado descartado na ingestão não pode ser reprocessado depois; usar só quando a perda é intencional.
