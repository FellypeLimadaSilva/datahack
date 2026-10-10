{% test dh_unique_combination(model, combination_of_columns) %}
    select {{ combination_of_columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ combination_of_columns | join(', ') }}
    having count(*) > 1
{% endtest %}

{% test dh_min_value(model, column_name, min_value=0) %}
    select {{ column_name }} from {{ model }} where {{ column_name }} < {{ min_value }}
{% endtest %}

{% test dh_invalid_ratio(model, column_name, max_ratio=0) %}
    select ratio
    from (
        select count(*) filter (where {{ column_name }} > 0)::numeric / nullif(count(*), 0) as ratio
        from {{ model }}
    ) x
    where ratio > {{ max_ratio }}
{% endtest %}

{% test dh_join_coverage(model, column_name, to, field, min_ratio=0.95) %}
    with chaves as (
        select distinct {{ column_name }} as chave
        from {{ model }}
        where {{ column_name }} is not null
    ),

    cobertura as (
        select
            count(*) as total,
            count(*) filter (
                where exists (select 1 from {{ to }} as t where t.{{ field }} = chaves.chave)
            ) as encontradas
        from chaves
    )

    select total, encontradas, encontradas::numeric / nullif(total, 0) as taxa
    from cobertura
    where encontradas::numeric / nullif(total, 0) < {{ min_ratio }}
{% endtest %}
