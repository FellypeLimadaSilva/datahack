with versao as (
    {{ dh_latest_partition(source('bronze', 'censo_ies'), 'nu_ano_censo') }}
)

select
    {{ dh_to_int('nu_ano_censo') }}::int as nu_ano_censo,
    {{ dh_clean_text('co_ies') }}::text as co_ies,
    {{ dh_clean_text('no_ies') }}::text as no_ies,
    {{ dh_clean_text('sg_ies') }}::text as sg_ies,
    {{ dh_clean_text('sg_uf_ies') }}::text as sg_uf_ies,
    {{ dh_clean_text('co_municipio_ies') }}::text as co_municipio_ies,
    {{ dh_to_int('tp_categoria_administrativa') }}::int as tp_categoria_administrativa,
    {{ dh_to_int('tp_organizacao_academica') }}::int as tp_organizacao_academica
from versao
