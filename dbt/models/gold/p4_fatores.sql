with cursos as (
    select *
    from {{ ref('int_curso_desistencia') }}
    where tem_cpc and qt_ingressante >= {{ var('min_base_ranking') }}
),

fatores as (
    select
        'CPC contínuo' as fator,
        corr(cpc_continuo, taxa_desistencia_marco) as r,
        count(cpc_continuo) as n
    from cursos
    union all
    select
        'Enade contínuo' as fator,
        corr(enade_continuo, taxa_desistencia_marco) as r,
        count(enade_continuo) as n
    from cursos
    union all
    select
        'IDD' as fator,
        corr(idd_padronizado, taxa_desistencia_marco) as r,
        count(idd_padronizado) as n
    from cursos
    union all
    select
        'Doutores' as fator,
        corr(doutores_padronizado, taxa_desistencia_marco) as r,
        count(doutores_padronizado) as n
    from cursos
    union all
    select
        'Regime de trabalho' as fator,
        corr(regime_trabalho_padronizado, taxa_desistencia_marco) as r,
        count(regime_trabalho_padronizado) as n
    from cursos
    union all
    select
        'Infraestrutura' as fator,
        corr(infraestrutura_padronizado, taxa_desistencia_marco) as r,
        count(infraestrutura_padronizado) as n
    from cursos
    union all
    select
        'Organização didático-pedagógica' as fator,
        corr(didatico_pedagogica_padronizado, taxa_desistencia_marco) as r,
        count(didatico_pedagogica_padronizado) as n
    from cursos
    union all
    select
        'Rede privada' as fator,
        corr((rede = 'Privada')::int, taxa_desistencia_marco) as r,
        count(rede) as n
    from cursos
)

select
    fator::text,
    round(r::numeric, 3) as correlacao_pearson,
    n::bigint as nu_cursos
from fatores
where n >= {{ var('min_cell') }}
