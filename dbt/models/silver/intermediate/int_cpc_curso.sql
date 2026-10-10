select distinct on (co_curso)
    co_curso,
    nu_edicao as nu_edicao_cpc,
    area_avaliacao,
    cpc_faixa,
    cpc_continuo,
    enade_continuo,
    idd_padronizado,
    doutores_padronizado,
    regime_trabalho_padronizado,
    infraestrutura_padronizado,
    didatico_pedagogica_padronizado
from {{ ref('stg_cpc') }}
where nu_edicao in ({{ var('cpc_edicoes') | join(', ') }})
order by co_curso, nu_edicao desc
