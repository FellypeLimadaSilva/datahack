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
