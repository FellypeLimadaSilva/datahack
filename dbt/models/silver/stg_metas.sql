with latest as (
    {{ dh_latest(source('bronze', 'metas'), ['loja_id', 'ano_mes']) }}
)

select
    {{ dh_to_int('loja_id') }}                                         as loja_id,
    {{ dh_safe_cast(dh_clean_text('ano_mes') ~ " || '-01'", 'date') }} as mes,
    {{ dh_to_numeric('valor_meta', decimal=',') }}                     as valor_meta,
    _dh_ingested_at
from latest
where {{ dh_to_int('loja_id') }} is not null
