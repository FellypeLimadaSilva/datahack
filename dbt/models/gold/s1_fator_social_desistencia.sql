with cursos as (
    select
        p.fator,
        p.share,
        d.co_curso,
        d.qt_ingressante,
        d.qt_base_marco,
        d.qt_desistencia_marco,
        ntile(4) over (partition by p.fator order by p.share) as quartil
    from {{ ref('int_curso_perfil_social') }} as p
    inner join {{ ref('int_curso_desistencia') }} as d on p.co_curso = d.co_curso
    where d.qt_ingressante >= {{ var('min_base_ranking') }}
),

correlacao as (
    select
        fator,
        corr(share, 100.0 * qt_desistencia_marco / nullif(qt_base_marco, 0)) as r
    from cursos
    group by fator
)

select
    c.fator::text,
    c.quartil::int as quartil,
    round(100 * min(c.share), 2)::numeric as pct_min,
    round(100 * max(c.share), 2)::numeric as pct_max,
    count(*)::bigint as nu_cursos,
    {{ dh_mask_count('sum(c.qt_ingressante)') }}::bigint as qt_ingressante,
    {{ dh_mask_count('sum(c.qt_desistencia_marco)') }}::bigint as qt_desistencia_marco,
    {{ dh_rate('sum(c.qt_desistencia_marco)', 'sum(c.qt_base_marco)') }}::numeric as taxa_desistencia_marco,
    round(max(r.r)::numeric, 3) as correlacao_pearson
from cursos as c
inner join correlacao as r on c.fator = r.fator
group by c.fator, c.quartil
having sum(c.qt_ingressante) >= {{ var('min_cell') }}
