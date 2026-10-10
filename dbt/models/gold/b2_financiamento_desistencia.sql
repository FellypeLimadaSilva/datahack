with financiamento as (
    select
        co_curso,
        sum(qt_mat_fies + qt_mat_prouni)::numeric / nullif(sum(qt_mat), 0) as share_financiado
    from {{ ref('int_censo_curso_ano') }}
    where tp_rede = 2
    group by co_curso
),

cursos as (
    select
        d.co_curso,
        d.qt_ingressante,
        d.qt_desistencia_marco,
        d.qt_base_marco,
        f.share_financiado,
        ntile(4) over (order by f.share_financiado) as quartil
    from {{ ref('int_curso_desistencia') }} as d
    inner join financiamento as f on d.co_curso = f.co_curso
    where
        d.rede = 'Privada'
        and d.qt_ingressante >= {{ var('min_base_ranking') }}
        and f.share_financiado is not null
)

select
    quartil::int as quartil_financiamento,
    round(100 * min(share_financiado), 2)::numeric as pct_financiado_min,
    round(100 * max(share_financiado), 2)::numeric as pct_financiado_max,
    count(*)::bigint as nu_cursos,
    {{ dh_mask_count('sum(qt_ingressante)') }}::bigint as qt_ingressante,
    {{ dh_mask_count('sum(qt_desistencia_marco)') }}::bigint as qt_desistencia_marco,
    {{ dh_rate('sum(qt_desistencia_marco)', 'sum(qt_base_marco)') }}::numeric as taxa_desistencia_marco
from cursos
group by quartil
having sum(qt_ingressante) >= {{ var('min_cell') }}
