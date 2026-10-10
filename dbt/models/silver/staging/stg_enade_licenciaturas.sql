{%- set existe = dh_relation_exists('bronze', 'enade_licenciaturas') -%}
{%- set c_ano = dh_pick_column('bronze', 'enade_licenciaturas', ['^ano$', '^nu_ano']) -%}
{%- set c_curso = dh_pick_column('bronze', 'enade_licenciaturas', ['^codigo_do_curso$', '^co_curso$', 'codigo.*curso']) -%}
{%- set c_ies = dh_pick_column('bronze', 'enade_licenciaturas', ['^codigo_da_ies$', '^co_ies$', 'codigo.*ies']) -%}
{%- set c_area = dh_pick_column('bronze', 'enade_licenciaturas', ['^area_de_avaliacao$', 'area.*avaliacao', '^no_area']) -%}
{%- set c_inscritos = dh_pick_column('bronze', 'enade_licenciaturas', ['concluintes_inscritos', 'inscritos']) -%}
{%- set c_participantes = dh_pick_column('bronze', 'enade_licenciaturas', ['concluintes_participantes$', 'participantes$', 'participantes']) -%}
{%- set c_proficiencia = dh_pick_column('bronze', 'enade_licenciaturas', ['(percentual|proporcao|perc|taxa).*profici', 'profici.*(percentual|proporcao|perc|taxa)', 'profici']) -%}
{%- set c_faixa = dh_pick_column('bronze', 'enade_licenciaturas', ['conceito.*faixa', 'faixa']) -%}
{%- set c_continuo = dh_pick_column('bronze', 'enade_licenciaturas', ['conceito.*continuo', 'continuo']) -%}

{%- if existe and execute and (c_curso is none or c_proficiencia is none) -%}
    {{ exceptions.raise_compiler_error(
        "bronze.enade_licenciaturas sem coluna de curso ou de proficiência reconhecida; "
        ~ "ajuste os padrões em stg_enade_licenciaturas.sql") }}
{%- endif -%}

{% if existe %}
with versao as (
    {%- if c_ano is not none %}
    {{ dh_latest_partition(source('bronze', 'enade_licenciaturas'), c_ano) }}
    {%- else %}
    select * from {{ source('bronze', 'enade_licenciaturas') }}
    {%- endif %}
),

tipado as (
    select
        {{ dh_typed_column(c_ano, 'int') }} as nu_edicao,
        {{ dh_typed_column(c_curso) }} as co_curso,
        {{ dh_typed_column(c_ies) }} as co_ies,
        {{ dh_typed_column(c_area) }} as area_avaliacao,
        {{ dh_typed_column(c_inscritos, 'bigint') }} as qt_concluinte_inscrito,
        {{ dh_typed_column(c_participantes, 'bigint') }} as qt_concluinte_participante,
        {{ dh_typed_column(c_proficiencia, 'numeric') }} as proficiencia_bruta,
        {{ dh_typed_column(c_faixa) }} as conceito_faixa,
        {{ dh_typed_column(c_continuo, 'numeric') }} as conceito_continuo
    from versao
)

select
    nu_edicao,
    co_curso,
    co_ies,
    area_avaliacao,
    qt_concluinte_inscrito,
    qt_concluinte_participante,
    case
        when max(proficiencia_bruta) over () <= 1 then proficiencia_bruta * 100
        else proficiencia_bruta
    end::numeric as pct_proficiente,
    conceito_faixa,
    conceito_continuo
from tipado
where co_curso is not null
{% else %}
select
    null::int as nu_edicao,
    null::text as co_curso,
    null::text as co_ies,
    null::text as area_avaliacao,
    null::bigint as qt_concluinte_inscrito,
    null::bigint as qt_concluinte_participante,
    null::numeric as pct_proficiente,
    null::text as conceito_faixa,
    null::numeric as conceito_continuo
where false
{% endif %}
