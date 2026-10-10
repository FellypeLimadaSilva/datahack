select
    t.*,
    sum(t.qt_desistencia) over w as qt_desistencia_acum,
    sum(t.qt_concluinte) over w as qt_concluinte_acum,
    sum(t.qt_falecido) over w as qt_falecido_acum,
    t.qt_ingressante - sum(t.qt_falecido) over w as qt_base_acum,
    max(t.nu_ano_referencia) over (partition by t.co_curso, t.nu_ano_ingresso) as nu_ultimo_ano_observado
from {{ ref('stg_trajetoria') }} as t
window w as (
    partition by t.co_curso, t.nu_ano_ingresso
    order by t.nu_ano_referencia
    rows between unbounded preceding and current row
)
