{{ config(indexes=[{'columns': ['mes', 'loja_id'], 'unique': true}]) }}

with venda_mes as (
    select
        date_trunc('month', data_venda)::date as mes,
        loja_id,
        sum(receita_liquida)                  as receita
    from {{ ref('mart_vendas_diarias') }}
    group by 1, 2
),

limites as (
    select
        min(mes) as mes_ini,
        max(mes) as mes_fim
    from venda_mes
),

grade as (
    select
        m.primeiro_dia_mes as mes,
        l.loja_id,
        l.data_inauguracao,
        l.data_fechamento
    from (select distinct primeiro_dia_mes from {{ ref('dim_data') }}) as m
    cross join limites
    cross join {{ ref('dim_loja') }} as l
    where m.primeiro_dia_mes between limites.mes_ini and limites.mes_fim
),

base as (
    select
        g.mes,
        g.loja_id,
        coalesce(v.receita, 0)                                                        as receita_liquida,
        coalesce(ly.receita, 0)                                                       as receita_liquida_ly,
        mt.valor_meta,
        (
            g.data_inauguracao <= (g.mes - make_interval(months => {{ var('l4l_min_months') }}))::date
            and (
                g.data_fechamento is null
                or g.data_fechamento >= (g.mes + interval '1 month - 1 day')::date
            )
        ) as is_comparavel_l4l
    from grade as g
    left join venda_mes as v on g.loja_id = v.loja_id and g.mes = v.mes
    left join venda_mes as ly on g.loja_id = ly.loja_id and ly.mes = (g.mes - interval '1 year')::date
    left join {{ ref('stg_metas') }} as mt on g.loja_id = mt.loja_id and g.mes = mt.mes
)

select
    mes,
    loja_id,
    receita_liquida,
    receita_liquida_ly,
    valor_meta,
    round(100.0 * receita_liquida / nullif(valor_meta, 0), 2) as atingimento_meta_pct,
    round(100.0 * (receita_liquida - receita_liquida_ly) / nullif(receita_liquida_ly, 0), 2)
        as crescimento_ly_pct,
    is_comparavel_l4l,
    case when is_comparavel_l4l then receita_liquida end      as receita_l4l,
    case when is_comparavel_l4l then receita_liquida_ly end   as receita_l4l_ly
from base
