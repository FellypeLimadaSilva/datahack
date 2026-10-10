with cursos as (
    select
        d.rede,
        d.qt_ingressante,
        d.qt_desistencia_final,
        d.qt_concluinte_final,
        e.qt_concluinte_participante,
        e.pct_proficiente
    from {{ ref('int_curso_desistencia') }} as d
    left join {{ ref('stg_enade_licenciaturas') }} as e on d.co_curso = e.co_curso
    where d.tp_grau_academico = 2
),

grupos as (
    select
        coalesce(rede, 'Total') as rede,
        count(*) as nu_cursos,
        sum(qt_ingressante) as qt_ingressante,
        sum(qt_desistencia_final) as qt_desistencia,
        sum(qt_concluinte_final) as qt_concluinte,
        count(pct_proficiente) as nu_cursos_enade,
        sum(qt_concluinte_participante) filter (where pct_proficiente is not null) as qt_participante_enade,
        sum(pct_proficiente * qt_concluinte_participante) filter (where pct_proficiente is not null)
        / nullif(sum(qt_concluinte_participante) filter (where pct_proficiente is not null), 0)
            as pct_proficiente
    from cursos
    group by grouping sets ((rede), ())
)

select
    rede::text,
    nu_cursos::bigint,
    {{ dh_mask_count('qt_ingressante') }}::bigint as qt_ingressante,
    {{ dh_rate('qt_desistencia', 'qt_ingressante') }}::numeric as de_100_desistem,
    {{ dh_rate('qt_concluinte', 'qt_ingressante') }}::numeric as de_100_concluem,
    nu_cursos_enade::bigint,
    {{ dh_mask_count('qt_participante_enade') }}::bigint as qt_participante_enade,
    case when qt_participante_enade >= {{ var('min_cell') }} then round(pct_proficiente, 2) end::numeric
        as pct_proficiente,
    case
        when qt_participante_enade >= {{ var('min_cell') }}
            then round({{ dh_rate('qt_concluinte', 'qt_ingressante') }} * pct_proficiente / 100, 2)
    end::numeric as de_100_concluem_proficientes
from grupos
where qt_ingressante >= {{ var('min_cell') }}
