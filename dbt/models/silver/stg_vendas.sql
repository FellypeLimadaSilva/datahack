{{
    config(
        materialized='incremental',
        unique_key=['venda_id', 'item_seq'],
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        indexes=[
            {'columns': ['venda_id', 'item_seq'], 'unique': true},
            {'columns': ['_dh_ingested_at'], 'type': 'brin'},
        ],
    )
}}

with src as (
    select * from {{ source('bronze', 'vendas') }}
    {% if is_incremental() %}
        where _dh_ingested_at > (
            select
                coalesce(max(_dh_ingested_at), '-infinity'::timestamptz)
                - interval '{{ var("incremental_lookback") }}'
            from {{ this }}
        )
    {% endif %}
),

latest as (
    {{ dh_latest('src', ['venda_id', 'item_seq']) }}
)

select
    {{ dh_to_int('venda_id') }}                        as venda_id,
    {{ dh_to_int('item_seq') }}::int                   as item_seq,
    {{ dh_to_timestamp('data_hora_venda') }}           as data_hora_venda,
    {{ dh_to_int('loja_id') }}                         as loja_id,
    {{ dh_to_int('produto_id') }}                      as produto_id,
    {{ dh_to_numeric('quantidade') }}                  as quantidade,
    {{ dh_to_numeric('valor_unitario') }}              as valor_unitario,
    coalesce({{ dh_to_numeric('valor_desconto') }}, 0) as valor_desconto,
    lower({{ dh_clean_text('canal') }})                as canal,
    lower({{ dh_clean_text('status') }})               as status,
    {{ dh_hash_pii('cliente_cpf', digits_only=true) }} as cliente_hash,
    {{ dh_clean_text('observacao') }}                  as observacao,
    _dh_ingested_at
from latest
where
    {{ dh_to_int('venda_id') }} is not null
    and {{ dh_to_int('item_seq') }} is not null
