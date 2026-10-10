{% if dh_relation_exists('bronze', 'ibge_populacao_idade_mt') %}
    select
        {{ dh_clean_text('co_municipio') }}::text as co_municipio,
        {{ dh_clean_text('no_municipio') }}::text as no_municipio,
        {{ dh_to_int('nu_ano') }}::int as nu_ano,
        {{ dh_clean_text('co_idade') }}::text as co_idade,
        {{ dh_clean_text('idade') }}::text as idade,
        {{ dh_to_int('qt_populacao') }}::bigint as nu_populacao
    from {{ source('bronze', 'ibge_populacao_idade_mt') }}
    where {{ dh_to_int('qt_populacao') }} is not null
{% else %}
    select
        null::text as co_municipio,
        null::text as no_municipio,
        null::int as nu_ano,
        null::text as co_idade,
        null::text as idade,
        null::bigint as nu_populacao
    where false
{% endif %}
