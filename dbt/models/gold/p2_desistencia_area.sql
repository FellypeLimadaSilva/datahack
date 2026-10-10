with base as (
    select
        coalesce(no_cine_area_geral, 'Não informada') as no_cine_area_geral,
        modalidade,
        nu_ano_ingresso,
        nu_ano_curso,
        count(distinct co_curso) as nu_cursos,
        sum(qt_ingressante) as qt_ingressante,
        sum(qt_desistencia_acum) as qt_desistencia_acum,
        sum(qt_concluinte_acum) as qt_concluinte_acum,
        sum(qt_base_acum) as qt_base_acum
    from {{ ref('int_trajetoria_acumulada') }}
    group by 1, 2, 3, 4
)

select
    no_cine_area_geral::text,
    modalidade::text,
    nu_ano_ingresso::int,
    nu_ano_curso::int,
    nu_cursos::bigint,
    {{ dh_mask_count('qt_ingressante') }}::bigint as qt_ingressante,
    {{ dh_mask_count('qt_desistencia_acum') }}::bigint as qt_desistencia_acum,
    {{ dh_rate('qt_desistencia_acum', 'qt_base_acum') }}::numeric as taxa_desistencia_acum,
    {{ dh_rate('qt_concluinte_acum', 'qt_base_acum') }}::numeric as taxa_conclusao_acum
from base
where qt_ingressante >= {{ var('min_cell') }}
