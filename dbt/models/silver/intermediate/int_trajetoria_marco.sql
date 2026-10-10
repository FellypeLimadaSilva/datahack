select
    co_curso,
    nu_ano_ingresso,
    min(no_curso) as no_curso,
    min(no_ies) as no_ies,
    min(rede) as rede,
    min(modalidade) as modalidade,
    min(tp_grau_academico) as tp_grau_academico,
    min(grau_academico) as grau_academico,
    min(no_cine_area_geral) as no_cine_area_geral,
    min(no_cine_rotulo) as no_cine_rotulo,
    max(qt_ingressante) as qt_ingressante,
    max(qt_desistencia_acum) filter (where nu_ano_curso = {{ var('ano_curso_comparacao') }})
        as qt_desistencia_marco,
    max(qt_concluinte_acum) filter (where nu_ano_curso = {{ var('ano_curso_comparacao') }})
        as qt_concluinte_marco,
    max(qt_base_acum) filter (where nu_ano_curso = {{ var('ano_curso_comparacao') }})
        as qt_base_marco,
    bool_or(nu_ano_curso = {{ var('ano_curso_comparacao') }}) as tem_marco,
    max(qt_desistencia_acum) filter (where nu_ano_referencia = nu_ultimo_ano_observado)
        as qt_desistencia_final,
    max(qt_concluinte_acum) filter (where nu_ano_referencia = nu_ultimo_ano_observado)
        as qt_concluinte_final,
    max(qt_permanencia) filter (where nu_ano_referencia = nu_ultimo_ano_observado)
        as qt_permanencia_final,
    max(qt_base_acum) filter (where nu_ano_referencia = nu_ultimo_ano_observado)
        as qt_base_final,
    max(nu_ultimo_ano_observado) as nu_ultimo_ano_observado
from {{ ref('int_trajetoria_acumulada') }}
group by co_curso, nu_ano_ingresso
