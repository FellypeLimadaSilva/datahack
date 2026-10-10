\pset pager off

\echo 'B2: FIES e ProUni por ano, rede privada presencial'
select
    nu_ano_censo,
    count(*) as cursos,
    count(*) filter (where qt_mat_fies is null) as cursos_sem_fies,
    count(*) filter (where qt_mat_prouni_integral is null or qt_mat_prouni_parcial is null) as cursos_sem_prouni,
    sum(qt_mat) as matriculas,
    sum(qt_mat_fies) as fies,
    sum(coalesce(qt_mat_prouni_integral, 0) + coalesce(qt_mat_prouni_parcial, 0)) as prouni
from silver.stg_censo_cursos
where tp_rede = 2 and tp_modalidade_ensino = 1 and tp_nivel_academico = 1
group by 1
order by 1;

with por_ies as (
    select
        c.nu_ano_censo,
        coalesce(i.no_ies, c.co_ies) as ies,
        sum(c.qt_mat_fies) as fies,
        row_number() over (partition by c.nu_ano_censo order by sum(c.qt_mat_fies) desc nulls last) as n
    from silver.stg_censo_cursos as c
    left join silver.stg_censo_ies as i on c.co_ies = i.co_ies and c.nu_ano_censo = i.nu_ano_censo
    where c.tp_rede = 2 and c.tp_modalidade_ensino = 1 and c.tp_nivel_academico = 1
    group by 1, 2
)
select nu_ano_censo, ies, fies from por_ies where n <= 5 order by 1, 3 desc;

\echo 'P3: 5 IES publicas com mais desvinculados por ano'
with por_ies as (
    select
        c.nu_ano_censo,
        coalesce(i.no_ies, c.co_ies) as ies,
        sum(c.qt_sit_desvinculado) as desvinculados,
        sum(c.qt_mat) as matriculas,
        row_number() over (partition by c.nu_ano_censo order by sum(c.qt_sit_desvinculado) desc) as n
    from silver.stg_censo_cursos as c
    left join silver.stg_censo_ies as i on c.co_ies = i.co_ies and c.nu_ano_censo = i.nu_ano_censo
    where c.tp_rede = 1 and c.tp_nivel_academico = 1
    group by 1, 2
)
select nu_ano_censo, ies, desvinculados, matriculas from por_ies where n <= 5 order by 1, 3 desc;

\echo 'B1: cursos presenciais de Sao Jose dos Quatro Marcos'
select c.nu_ano_censo, coalesce(i.no_ies, c.co_ies) as ies, c.no_curso, c.nu_vagas, c.qt_ing, c.qt_mat
from silver.stg_censo_cursos as c
left join silver.stg_censo_ies as i on c.co_ies = i.co_ies and c.nu_ano_censo = i.nu_ano_censo
where c.no_municipio ilike 'S_o Jos_ dos Quatro Marcos%' and c.tp_modalidade_ensino = 1
    and c.nu_ano_censo = (select max(nu_ano_censo) from silver.stg_censo_cursos)
order by c.nu_vagas desc
limit 10;
