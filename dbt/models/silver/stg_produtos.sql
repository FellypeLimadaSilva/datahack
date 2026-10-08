with latest as (
    {{ dh_latest(source('bronze', 'produtos'), ['produto_id']) }}
)

select
    {{ dh_to_int('produto_id') }}                 as produto_id,
    {{ dh_clean_text('sku') }}                    as sku,
    {{ dh_clean_text('nome') }}                   as nome_produto,
    {{ dh_clean_text('categoria_departamento') }} as departamento,
    {{ dh_clean_text('categoria_nome') }}         as categoria,
    {{ dh_to_numeric('preco_lista') }}            as preco_lista,
    coalesce({{ dh_to_bool('ativo') }}, false)    as is_ativo,
    coalesce(tags, '[]') <> '[]'                  as is_promocional,
    {{ dh_to_timestamp('atualizado_em') }}        as atualizado_em,
    _dh_ingested_at
from latest
where {{ dh_to_int('produto_id') }} is not null
