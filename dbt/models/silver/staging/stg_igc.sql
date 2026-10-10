with versao as (
    {{ dh_latest_partition(source('bronze', 'igc'), 'ano') }}
)

select
    {{ dh_to_int('ano') }}::int as nu_edicao,
    {{ dh_clean_text('codigo_da_ies') }}::text as co_ies,
    {{ dh_clean_text('nome_da_ies') }}::text as no_ies,
    {{ dh_clean_text('sigla_da_uf') }}::text as sg_uf,
    {{ dh_to_numeric('igc_continuo', 'auto') }}::numeric as igc_continuo,
    case
        when {{ dh_clean_text('igc_faixa') }} in ('1', '2', '3', '4', '5') then {{ dh_clean_text('igc_faixa') }}
        when upper({{ dh_clean_text('igc_faixa') }}) = 'SC' then 'SC'
    end::text as igc_faixa
from versao
