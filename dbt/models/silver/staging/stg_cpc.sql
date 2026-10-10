with versao as (
    {{ dh_latest_partition(source('bronze', 'cpc'), 'ano') }}
)

select
    {{ dh_to_int('ano') }}::int as nu_edicao,
    {{ dh_clean_text('codigo_do_curso') }}::text as co_curso,
    {{ dh_clean_text('codigo_da_ies') }}::text as co_ies,
    {{ dh_clean_text('codigo_da_area') }}::text as co_area_avaliacao,
    {{ dh_clean_text('area_de_avaliacao') }}::text as area_avaliacao,
    {{ dh_clean_text('sigla_da_uf') }}::text as sg_uf,
    {{ dh_to_int('no_de_concluintes_inscritos') }}::bigint as qt_concluinte_inscrito,
    {{ dh_to_int('no_de_concluintes_participantes') }}::bigint as qt_concluinte_participante,
    {{ dh_to_numeric('conceito_enade_continuo', 'auto') }}::numeric as enade_continuo,
    {{ dh_to_numeric('nota_padronizada_idd', 'auto') }}::numeric as idd_padronizado,
    {{ dh_to_numeric('nota_padronizada_doutores', 'auto') }}::numeric as doutores_padronizado,
    {{ dh_to_numeric('nota_padronizada_regime_de_trabalho', 'auto') }}::numeric as regime_trabalho_padronizado,
    {{ dh_to_numeric('nota_padronizada_infraestrutura_e_instalacoes_fisicas', 'auto') }}::numeric
        as infraestrutura_padronizado,
    {{ dh_to_numeric('nota_padronizada_organizacao_didatico_pedagogica', 'auto') }}::numeric
        as didatico_pedagogica_padronizado,
    {{ dh_to_numeric('cpc_continuo', 'auto') }}::numeric as cpc_continuo,
    case
        when {{ dh_clean_text('cpc_faixa') }} in ('1', '2', '3', '4', '5') then {{ dh_clean_text('cpc_faixa') }}
        when upper({{ dh_clean_text('cpc_faixa') }}) = 'SC' then 'SC'
    end::text as cpc_faixa
from versao
