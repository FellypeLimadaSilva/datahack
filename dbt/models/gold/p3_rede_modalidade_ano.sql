with base as (
    select
        nu_ano_censo,
        rede,
        modalidade,
        count(*) as nu_cursos,
        sum(nu_vagas) as nu_vagas,
        sum(qt_ing) as qt_ingressante,
        sum(qt_mat) as qt_matricula,
        sum(qt_conc) as qt_concluinte,
        sum(qt_sit_trancada) as qt_trancada,
        sum(qt_sit_desvinculado) as qt_desvinculado,
        sum(qt_sit_transferido) as qt_transferido,
        sum(qt_sit_falecido) as qt_falecido
    from {{ ref('int_censo_curso_ano') }}
    group by nu_ano_censo, rede, modalidade
),

taxas as (
    select
        *,
        qt_matricula + qt_trancada + qt_desvinculado + qt_transferido + qt_falecido as qt_vinculo,
        {{ dh_rate('qt_desvinculado', 'qt_matricula + qt_trancada + qt_desvinculado + qt_transferido + qt_falecido') }}
            as taxa_evasao_anual,
        {{ dh_rate('qt_trancada', 'qt_matricula + qt_trancada + qt_desvinculado + qt_transferido + qt_falecido') }}
            as taxa_trancamento
    from base
)

select
    nu_ano_censo::int,
    rede::text,
    modalidade::text,
    nu_cursos::bigint,
    nu_vagas::bigint,
    {{ dh_mask_count('qt_ingressante') }}::bigint as qt_ingressante,
    {{ dh_mask_count('qt_matricula') }}::bigint as qt_matricula,
    {{ dh_mask_count('qt_concluinte') }}::bigint as qt_concluinte,
    {{ dh_mask_count('qt_trancada') }}::bigint as qt_trancada,
    {{ dh_mask_count('qt_desvinculado') }}::bigint as qt_desvinculado,
    {{ dh_mask_count('qt_transferido') }}::bigint as qt_transferido,
    {{ dh_mask_count('qt_vinculo') }}::bigint as qt_vinculo,
    taxa_evasao_anual::numeric,
    taxa_trancamento::numeric,
    (taxa_evasao_anual - lag(taxa_evasao_anual) over (
        partition by rede, modalidade order by nu_ano_censo
    ))::numeric as variacao_evasao_pp,
    round((100.0 * qt_matricula / nullif(lag(qt_matricula) over (
        partition by rede, modalidade order by nu_ano_censo
    ), 0) - 100)::numeric, 2) as variacao_matricula_pct
from taxas
where qt_vinculo >= {{ var('min_cell') }}
