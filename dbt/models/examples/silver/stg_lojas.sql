with latest as (
    {{ dh_latest(source('bronze', 'lojas'), ['loja_id']) }}
)

select
    {{ dh_to_int('loja_id') }}                  as loja_id,
    {{ dh_clean_text('nome_da_loja') }}         as nome_loja,
    {{ dh_clean_text('cidade') }}               as cidade,
    upper({{ dh_clean_text('uf') }})            as uf,
    {{ dh_clean_text('regiao') }}               as regiao,
    {{ dh_to_date('data_inauguracao', 'dmy') }} as data_inauguracao,
    {{ dh_to_date('data_fechamento', 'dmy') }}  as data_fechamento,
    {{ dh_to_numeric('area_m2') }}              as area_m2,
    _dh_ingested_at
from latest
where {{ dh_to_int('loja_id') }} is not null
