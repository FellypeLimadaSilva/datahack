{% test dh_unique_combination(model, combination_of_columns) %}
    select {{ combination_of_columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ combination_of_columns | join(', ') }}
    having count(*) > 1
{% endtest %}

{% test dh_min_value(model, column_name, min_value=0) %}
    select {{ column_name }} from {{ model }} where {{ column_name }} < {{ min_value }}
{% endtest %}

{% test dh_between(model, column_name, min_value, max_value) %}
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}

{% test dh_no_small_cells(model) %}
    {%- set cols = [] -%}
    {%- for c in adapter.get_columns_in_relation(model) -%}
        {%- if c.name.startswith('qt_') -%}
            {%- do cols.append(c.name) -%}
        {%- endif -%}
    {%- endfor -%}
    {%- if cols | length == 0 -%}
        select 1 where false
    {%- else -%}
        select *
        from {{ model }}
        where {% for c in cols %}({{ c }} between 1 and {{ var('min_cell') }} - 1){% if not loop.last %} or {% endif %}{% endfor %}
    {%- endif -%}
{% endtest %}

{% test dh_row_count_equal(model, compare_model, model_filter='true', compare_filter='true') %}
    with a as (select count(*) as n from {{ model }} where {{ model_filter }}),
    b as (select count(*) as n from {{ compare_model }} where {{ compare_filter }})
    select a.n as modelo, b.n as referencia from a cross join b where a.n <> b.n
{% endtest %}

{% test dh_sum_equal(model, column_name, compare_model, compare_column, model_filter='true', compare_filter='true') %}
    with a as (select coalesce(sum({{ column_name }}), 0) as s from {{ model }} where {{ model_filter }}),
    b as (select coalesce(sum({{ compare_column }}), 0) as s from {{ compare_model }} where {{ compare_filter }})
    select a.s as modelo, b.s as referencia from a cross join b where a.s <> b.s
{% endtest %}

{% test dh_flow_balance(model) %}
    select *
    from {{ model }}
    where qt_permanencia + qt_concluinte_acum + qt_desistencia_acum + qt_falecido_acum <> qt_ingressante
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
