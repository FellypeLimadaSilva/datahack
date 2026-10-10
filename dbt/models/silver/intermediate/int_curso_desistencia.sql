with trajetoria as (
    select
        co_curso,
        min(no_curso) as no_curso,
        min(no_ies) as no_ies,
        min(rede) as rede,
        min(modalidade) as modalidade,
        min(tp_grau_academico) as tp_grau_academico,
        min(grau_academico) as grau_academico,
        min(no_cine_area_geral) as no_cine_area_geral,
        count(*) as nu_coortes,
        min(nu_ano_ingresso) as nu_primeira_coorte,
        max(nu_ano_ingresso) as nu_ultima_coorte,
        sum(qt_ingressante) as qt_ingressante,
        sum(qt_desistencia_marco) as qt_desistencia_marco,
        sum(qt_base_marco) as qt_base_marco,
        sum(qt_base_final) as qt_base_final,
        sum(qt_concluinte_final) as qt_concluinte_final,
        sum(qt_desistencia_final) as qt_desistencia_final
    from {{ ref('int_trajetoria_marco') }}
    where tem_marco
    group by co_curso
)

select
    t.*,
    round((100.0 * t.qt_desistencia_marco / nullif(t.qt_base_marco, 0))::numeric, 2)
        as taxa_desistencia_marco,
    c.nu_edicao_cpc,
    c.cpc_faixa,
    c.cpc_continuo,
    c.enade_continuo,
    c.idd_padronizado,
    c.doutores_padronizado,
    c.regime_trabalho_padronizado,
    c.infraestrutura_padronizado,
    c.didatico_pedagogica_padronizado,
    c.co_curso is not null as tem_cpc
from trajetoria as t
left join {{ ref('int_cpc_curso') }} as c on t.co_curso = c.co_curso
