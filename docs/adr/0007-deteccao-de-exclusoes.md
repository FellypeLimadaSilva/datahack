# ADR 0007 — Detecção de exclusões com trava de segurança

- **Status:** aceito · **Data:** 2026-10-08

## Contexto
Merge por chave não percebe registros apagados na origem, gerando números inflados na Gold.

## Decisão
`delete_detection` por snapshot completo ou por consulta de chaves. Exclusão lógica (`_dh_deleted_at`) como padrão,
física opcional. A operação roda na mesma transação da carga e é abortada se exceder `max_delete_ratio`.

## Consequências
+ Gold reflete exclusões, inclusive em modelos incrementais (soft atualiza `_dh_ingested_at`).
+ Extração quebrada não apaga a base.
− `hard` não propaga para incrementais já materializados; exige `--full-refresh` nesses modelos.
