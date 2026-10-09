{{ config(indexes=[
    {'columns': ['data_foto', 'loja_id', 'produto_id'], 'unique': true},
    {'columns': ['loja_id', 'data_foto']},
]) }}

select
    e.data_foto,
    date_trunc('month', e.data_foto)::date                                              as mes,
    e.loja_id,
    e.produto_id,
    e.quantidade_estoque,
    e.data_foto = max(e.data_foto) over (partition by date_trunc('month', e.data_foto)) as is_ultima_foto_mes
from {{ ref('stg_estoque_foto') }} as e
