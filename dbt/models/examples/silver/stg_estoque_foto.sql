with latest as (
    {{ dh_latest(source('bronze', 'estoque_foto'), ['data_foto', 'loja_id', 'produto_id']) }}
)

select
    {{ dh_to_date('data_foto') }}             as data_foto,
    {{ dh_to_int('loja_id') }}                as loja_id,
    {{ dh_to_int('produto_id') }}             as produto_id,
    {{ dh_to_numeric('quantidade_estoque') }} as quantidade_estoque,
    _dh_ingested_at
from latest
where {{ dh_to_date('data_foto') }} is not null
