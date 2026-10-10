with base as (
    select
        modalidade,
        nu_ano_ingresso,
        nu_ano_referencia,
        nu_ano_curso,
        count(distinct co_curso) as nu_cursos,
        sum(qt_ingressante) as qt_ingressante,
        sum(qt_permanencia) as qt_permanencia,
        sum(qt_concluinte) as qt_concluinte_ano,
        sum(qt_desistencia) as qt_desistencia_ano,
        sum(qt_falecido) as qt_falecido_ano,
        sum(qt_concluinte_acum) as qt_concluinte_acum,
        sum(qt_desistencia_acum) as qt_desistencia_acum,
        sum(qt_falecido_acum) as qt_falecido_acum
    from {{ ref('int_trajetoria_acumulada') }}
    group by modalidade, nu_ano_ingresso, nu_ano_referencia, nu_ano_curso
),

taxas as (
    select
        *,
        {{ dh_rate('qt_desistencia_acum', 'qt_ingressante') }} as taxa_desistencia_acum,
        {{ dh_rate('qt_concluinte_acum', 'qt_ingressante') }} as taxa_conclusao_acum,
        {{ dh_rate('qt_permanencia', 'qt_ingressante') }} as taxa_permanencia,
        {{ dh_rate('qt_desistencia_ano', 'qt_ingressante') }} as taxa_desistencia_ano,
        {{ dh_rate('qt_desistencia_ano', 'qt_permanencia + qt_concluinte_ano + qt_desistencia_ano + qt_falecido_ano') }}
            as taxa_desistencia_sobre_ativos,
        rank() over (
            partition by modalidade, nu_ano_ingresso order by qt_desistencia_ano desc
        ) = 1 as is_ano_maior_perda
    from base
)

select
    modalidade::text,
    nu_ano_ingresso::int,
    nu_ano_referencia::int,
    nu_ano_curso::int,
    nu_cursos::bigint,
    {{ dh_mask_count('qt_ingressante') }}::bigint as qt_ingressante,
    {{ dh_mask_count('qt_permanencia') }}::bigint as qt_permanencia,
    {{ dh_mask_count('qt_concluinte_ano') }}::bigint as qt_concluinte_ano,
    {{ dh_mask_count('qt_desistencia_ano') }}::bigint as qt_desistencia_ano,
    {{ dh_mask_count('qt_concluinte_acum') }}::bigint as qt_concluinte_acum,
    {{ dh_mask_count('qt_desistencia_acum') }}::bigint as qt_desistencia_acum,
    {{ dh_mask_count('qt_falecido_acum') }}::bigint as qt_falecido_acum,
    taxa_desistencia_acum::numeric,
    taxa_conclusao_acum::numeric,
    taxa_permanencia::numeric,
    taxa_desistencia_ano::numeric,
    taxa_desistencia_sobre_ativos::numeric,
    is_ano_maior_perda::boolean
from taxas
where qt_ingressante >= {{ var('min_cell') }}
