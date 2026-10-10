select
    co_curso::text,
    nu_ano_ingresso::int,
    no_curso::text,
    no_ies::text,
    rede::text,
    modalidade::text,
    grau_academico::text,
    no_cine_area_geral::text,
    no_cine_rotulo::text,
    {{ var('ano_curso_comparacao') }}::int as nu_ano_curso_marco,
    {{ dh_mask_count('qt_ingressante') }}::bigint as qt_ingressante,
    {{ dh_mask_count('qt_desistencia_marco') }}::bigint as qt_desistencia_marco,
    {{ dh_rate('qt_desistencia_marco', 'qt_ingressante') }}::numeric as taxa_desistencia_marco,
    {{ dh_rate('qt_concluinte_marco', 'qt_ingressante') }}::numeric as taxa_conclusao_marco,
    nu_ultimo_ano_observado::int,
    {{ dh_rate('qt_desistencia_final', 'qt_ingressante') }}::numeric as taxa_desistencia_final,
    {{ dh_rate('qt_concluinte_final', 'qt_ingressante') }}::numeric as taxa_conclusao_final,
    (qt_ingressante >= {{ var('min_base_ranking') }})::boolean as is_elegivel_ranking
from {{ ref('int_trajetoria_marco') }}
where
    qt_ingressante >= {{ var('min_cell') }}
    and tem_marco
