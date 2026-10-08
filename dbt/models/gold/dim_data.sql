{{ config(
    contract={'enforced': true},
    indexes=[{'columns': ['ano_mes']}],
) }}

with dias as (
    select d::date as data
    from generate_series(
        '{{ var("calendar_start") }}'::date, '{{ var("calendar_end") }}'::date, interval '1 day'
    ) as g (d)
),

anos as (
    select distinct extract(year from data)::int as ano from dias
),

moveis as (
    select
        p.pascoa + o.desloc as data,
        o.nome_feriado,
        o.tipo_feriado
    from anos
    cross join lateral (select {{ dh_easter_sunday('anos.ano') }} as pascoa) as p
    cross join (
        values
        (-48, 'Carnaval (segunda-feira)', 'ponto_facultativo'),
        (-47, 'Carnaval (terça-feira)', 'ponto_facultativo'),
        (-2, 'Sexta-feira Santa', 'nacional'),
        (0, 'Páscoa', 'nacional'),
        (60, 'Corpus Christi', 'ponto_facultativo')
    ) as o (desloc, nome_feriado, tipo_feriado)
),

fixos as (
    select
        make_date(a.ano, f.mes, f.dia) as data,
        f.nome_feriado,
        f.tipo_feriado
    from anos as a
    cross join {{ ref('feriados_fixos') }} as f
),

feriados as (
    select
        data,
        string_agg(nome_feriado, ' / ' order by nome_feriado) as nome_feriado,
        min(tipo_feriado)                                     as tipo_feriado
    from (
        select * from moveis
        union all
        select * from fixos
    ) as u
    group by data
)

select
    d.data::date                                                                                                          as data,
    extract(year from d.data)::int                                                                                        as ano,
    extract(quarter from d.data)::int                                                                                     as trimestre,
    extract(month from d.data)::int                                                                                       as mes,
    (array[
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
        'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ])[extract(month from d.data
    )::int]::text                                                                                                         as nome_mes,
    to_char(d.data, 'YYYY-MM')::text                                                                                      as ano_mes,
    date_trunc('month', d.data)::date                                                                                     as primeiro_dia_mes,
    extract(day from d.data)::int                                                                                         as dia,
    extract(isodow from d.data)::int                                                                                      as dia_semana_iso,
    (array['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'])[extract(isodow from d.data)::int]::text as nome_dia_semana,
    extract(week from d.data)::int                                                                                        as semana_iso,
    extract(isoyear from d.data)::int                                                                                     as ano_iso,
    (extract(isodow from d.data) >= 6)::boolean                                                                           as is_fim_de_semana,
    (f.data is not null)::boolean                                                                                         as is_feriado,
    f.nome_feriado::text                                                                                                  as nome_feriado,
    f.tipo_feriado::text                                                                                                  as tipo_feriado,
    (
        extract(isodow from d.data) < 6
        and coalesce(f.tipo_feriado, '') <> 'nacional'
    )::boolean                                                                                                            as is_dia_util,
    (d.data - interval '1 year')::date                                                                                    as data_ano_anterior,
    (d.data - 364)::date                                                                                                  as data_mesmo_dia_semana_ano_anterior
from dias as d
left join feriados as f on d.data = f.data
