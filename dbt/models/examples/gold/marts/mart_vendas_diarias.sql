{{ config(indexes=[
    {'columns': ['data_venda', 'loja_id', 'canal'], 'unique': true},
    {'columns': ['loja_id', 'data_venda']},
]) }}

select
    data_venda,
    loja_id,
    canal,
    count(*)                                                           as qtd_itens,
    count(distinct venda_id)                                           as qtd_cupons,
    count(distinct cliente_hash)                                       as qtd_clientes_identificados,
    sum(quantidade)                                                    as quantidade,
    sum(valor_bruto)                                                   as receita_bruta,
    sum(valor_desconto)                                                as desconto,
    sum(valor_liquido)                                                 as receita_liquida,
    round(sum(valor_liquido) / nullif(count(distinct venda_id), 0), 2) as ticket_medio
from {{ ref('fact_vendas') }}
where not is_cancelada and not is_excluida
group by data_venda, loja_id, canal
