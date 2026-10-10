select
    (case when cpc_faixa is null then 'Não avaliado' when cpc_faixa = 'SC' then 'Sem conceito (SC)' else cpc_faixa end)::text as cpc_faixa,
    rede::text,
    count(*)::bigint as nu_cursos,
    {{ dh_mask_count('sum(qt_ingressante)') }}::bigint as qt_ingressante,
    {{ dh_mask_count('sum(qt_desistencia_marco)') }}::bigint as qt_desistencia_marco,
    {{ dh_rate('sum(qt_desistencia_marco)', 'sum(qt_base_marco)') }}::numeric as taxa_desistencia_marco
from {{ ref('int_curso_desistencia') }}
group by 1, 2
having sum(qt_ingressante) >= {{ var('min_cell') }}
