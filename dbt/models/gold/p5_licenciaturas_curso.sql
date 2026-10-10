select
    d.co_curso::text,
    d.no_curso::text,
    d.no_ies::text,
    d.rede::text,
    d.modalidade::text,
    d.no_cine_area_geral::text,
    d.nu_coortes::bigint,
    {{ dh_mask_count('d.qt_ingressante') }}::bigint as qt_ingressante,
    d.taxa_desistencia_marco::numeric,
    {{ dh_rate('d.qt_desistencia_final', 'd.qt_base_final') }}::numeric as taxa_desistencia_final,
    {{ dh_rate('d.qt_concluinte_final', 'd.qt_base_final') }}::numeric as taxa_conclusao_final,
    e.area_avaliacao::text as area_enade,
    {{ dh_mask_count('e.qt_concluinte_participante') }}::bigint as qt_participante_enade,
    {{ dh_mask_count('e.qt_concluinte_proficiente') }}::bigint as qt_proficiente_enade,
    case when e.qt_concluinte_participante >= {{ var('min_cell') }} then e.pct_proficiente end::numeric
        as pct_proficiente,
    e.conceito_faixa::text as conceito_enade_faixa,
    (e.co_curso is not null)::boolean as tem_enade
from {{ ref('int_curso_desistencia') }} as d
left join {{ ref('stg_enade_licenciaturas') }} as e on d.co_curso = e.co_curso
where
    d.tp_grau_academico = 2
    and d.qt_ingressante >= {{ var('min_cell') }}
