with f as (
    select coalesce(sum(valor_liquido), 0) as v from {{ ref('fact_vendas') }} where not is_cancelada and not is_excluida
),
m as (
    select coalesce(sum(receita_liquida), 0) as v from {{ ref('mart_vendas_diarias') }}
)
select f.v as fato, m.v as mart
from f cross join m
where abs(f.v - m.v) > 0.01
