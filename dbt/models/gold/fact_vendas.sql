{{
    config(
        materialized='incremental',
        unique_key=['venda_id', 'item_seq'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        contract={'enforced': true},
        indexes=[
            {'columns': ['venda_id', 'item_seq'], 'unique': true},
            {'columns': ['data_venda']},
            {'columns': ['loja_id', 'data_venda']},
            {'columns': ['produto_id']},
            {'columns': ['_dh_ingested_at'], 'type': 'brin'},
        ],
    )
}}

with v as (
    select * from {{ ref('stg_vendas') }}
    {% if is_incremental() %}
        where _dh_ingested_at > (
            select
                coalesce(max(_dh_ingested_at), '-infinity'::timestamptz)
                - interval '{{ var("incremental_lookback") }}'
            from {{ this }}
        )
    {% endif %}
)

select
    v.venda_id::bigint                                                           as venda_id,
    v.item_seq::int                                                              as item_seq,
    v.data_hora_venda::date                                                      as data_venda,
    v.data_hora_venda::timestamp                                                 as data_hora_venda,
    v.loja_id::bigint                                                            as loja_id,
    v.produto_id::bigint                                                         as produto_id,
    v.canal::text                                                                as canal,
    v.status::text                                                               as status,
    (v.status = 'cancelada')::boolean                                            as is_cancelada,
    v.cliente_hash::text                                                         as cliente_hash,
    v.quantidade::numeric(18, 3)                                                 as quantidade,
    v.valor_unitario::numeric(18, 4)                                             as valor_unitario,
    round(v.quantidade * v.valor_unitario, 2)::numeric(18, 2)                    as valor_bruto,
    v.valor_desconto::numeric(18, 2)                                             as valor_desconto,
    round(v.quantidade * v.valor_unitario - v.valor_desconto, 2)::numeric(18, 2) as valor_liquido,
    v._dh_ingested_at::timestamptz                                               as _dh_ingested_at,
    now()::timestamptz                                                           as _dbt_loaded_at
from v
