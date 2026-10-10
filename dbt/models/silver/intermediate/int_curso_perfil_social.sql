with censo as (
    select
        co_curso,
        sum(qt_mat) as qt_mat,
        sum(qt_mat_escola_publica) as qt_mat_escola_publica,
        sum(qt_mat_reserva_vaga) as qt_mat_reserva_vaga,
        sum(qt_mat_apoio_social) as qt_mat_apoio_social,
        sum(qt_mat_noturno) as qt_mat_noturno,
        sum(qt_mat_fies + qt_mat_prouni) as qt_mat_financiada,
        sum(qt_mat_ppi) as qt_mat_ppi,
        sum(qt_mat_cor_declarada) as qt_mat_cor_declarada
    from {{ ref('int_censo_curso_ano') }}
    group by co_curso
),

fatores as (
    select
        co_curso,
        'Escola pública no ensino médio' as fator,
        qt_mat_escola_publica::numeric / nullif(qt_mat, 0) as share
    from censo
    union all
    select
        co_curso,
        'Reserva de vagas (cotas)' as fator,
        qt_mat_reserva_vaga::numeric / nullif(qt_mat, 0) as share
    from censo
    union all
    select
        co_curso,
        'Apoio social' as fator,
        qt_mat_apoio_social::numeric / nullif(qt_mat, 0) as share
    from censo
    union all
    select
        co_curso,
        'Turno noturno' as fator,
        qt_mat_noturno::numeric / nullif(qt_mat, 0) as share
    from censo
    union all
    select
        co_curso,
        'FIES ou ProUni' as fator,
        qt_mat_financiada::numeric / nullif(qt_mat, 0) as share
    from censo
    union all
    select
        co_curso,
        'Pretos, pardos e indígenas' as fator,
        qt_mat_ppi::numeric / nullif(qt_mat_cor_declarada, 0) as share
    from censo
)

select
    f.co_curso,
    f.fator,
    least(f.share, 1) as share
from fatores as f
where f.share is not null
