# ADR 0001 — ELT em camadas medalhão (Bronze/Silver/Gold)

- **Status:** aceito · **Data:** 2026-10-08

## Contexto
Fontes heterogêneas e desconhecidas até o dia do evento; necessidade de reprocessar sem voltar à origem
e de auditar a diferença entre dado bruto e dado publicado.

## Decisão
ELT medalhão: Bronze fiel à origem (texto + metadados), Silver tipada/deduplicada/pseudonimizada,
Gold dimensional e marts. BI consome somente Gold.

## Consequências
+ Reprocessamento sem reextração; trilha completa origem → número publicado.
+ Responsabilidades separadas por role e schema.
− Mais armazenamento (Bronze guarda tudo); mitigado por expurgo e `sink: parquet` em alto volume.
