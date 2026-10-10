with populacao as (
    select
        co_municipio,
        min(no_municipio) as no_municipio,
        sum(nu_populacao) as nu_populacao_18_24
    from {{ ref('stg_ibge_populacao') }}
    group by co_municipio
),

ano as (
    select max(nu_ano_censo) as nu_ano_censo from {{ ref('stg_censo_cursos') }}
),

vagas as (
    select
        c.co_municipio,
        count(distinct c.co_curso) as nu_cursos_presenciais,
        sum(c.nu_vagas) as nu_vagas_presenciais
    from {{ ref('stg_censo_cursos') }} as c
    inner join ano as a on c.nu_ano_censo = a.nu_ano_censo
    where c.tp_modalidade_ensino = 1 and c.tp_nivel_academico = 1
    group by c.co_municipio
)

select
    p.co_municipio::text,
    p.no_municipio::text,
    (select nu_ano_censo from ano)::int as nu_ano_censo,
    p.nu_populacao_18_24::bigint,
    coalesce(v.nu_cursos_presenciais, 0)::bigint as nu_cursos_presenciais,
    coalesce(v.nu_vagas_presenciais, 0)::bigint as nu_vagas_presenciais,
    round((100.0 * coalesce(v.nu_vagas_presenciais, 0) / nullif(p.nu_populacao_18_24, 0))::numeric, 2)
        as vagas_por_100_jovens,
    (coalesce(v.nu_vagas_presenciais, 0) = 0)::boolean as is_deserto
from populacao as p
left join vagas as v on p.co_municipio = v.co_municipio
