with base as (
    select
        nu_ano_censo,
        modalidade,
        count(*) as nu_cursos,
        sum(qt_ing) as qt_ingressante,
        sum(qt_ing_fies) as qt_ingressante_fies,
        sum(qt_ing_prouni) as qt_ingressante_prouni,
        sum(qt_mat) as qt_matricula,
        sum(qt_mat_fies) as qt_matricula_fies,
        sum(qt_mat_prouni) as qt_matricula_prouni
    from {{ ref('int_censo_curso_ano') }}
    where tp_rede = 2
    group by nu_ano_censo, modalidade
)

select
    nu_ano_censo::int,
    modalidade::text,
    nu_cursos::bigint,
    {{ dh_mask_count('qt_ingressante') }}::bigint as qt_ingressante,
    {{ dh_mask_count('qt_ingressante_fies') }}::bigint as qt_ingressante_fies,
    {{ dh_mask_count('qt_ingressante_prouni') }}::bigint as qt_ingressante_prouni,
    {{ dh_mask_count('qt_matricula') }}::bigint as qt_matricula,
    {{ dh_mask_count('qt_matricula_fies') }}::bigint as qt_matricula_fies,
    {{ dh_mask_count('qt_matricula_prouni') }}::bigint as qt_matricula_prouni,
    {{ dh_rate('qt_ingressante_fies', 'qt_ingressante') }}::numeric as pct_ingressante_fies,
    {{ dh_rate('qt_ingressante_prouni', 'qt_ingressante') }}::numeric as pct_ingressante_prouni,
    {{ dh_rate('qt_matricula_fies', 'qt_matricula') }}::numeric as pct_matricula_fies,
    {{ dh_rate('qt_matricula_prouni', 'qt_matricula') }}::numeric as pct_matricula_prouni
from base
where qt_matricula >= {{ var('min_cell') }}
