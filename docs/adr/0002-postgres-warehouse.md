# ADR 0002 — PostgreSQL 16 como warehouse padrão

- **Status:** aceito · **Data:** 2026-10-08

## Contexto
Ambiente local, sem custo de nuvem, conectável ao Power BI, com setup em minutos.

## Decisão
PostgreSQL 16 (`pg_input_is_valid`, `MERGE`, paralelismo, BRIN), configuração analítica em
`infra/postgres/postgresql.conf`, roles de menor privilégio e schemas por camada.

## Consequências
+ Zero custo, SQL padrão, ecossistema maduro, dbt-postgres estável.
− Escala vertical: acima de ~1 TB migrar fatos para lake + engine distribuída (ver ARCHITECTURE §6).
  Models dbt e macros foram escritos para facilitar a troca de adapter.
