{% test dh_unique_combination(model, combination_of_columns) %}
    select {{ combination_of_columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ combination_of_columns | join(', ') }}
    having count(*) > 1
{% endtest %}

{% test dh_min_value(model, column_name, min_value=0) %}
    select {{ column_name }} from {{ model }} where {{ column_name }} < {{ min_value }}
{% endtest %}
