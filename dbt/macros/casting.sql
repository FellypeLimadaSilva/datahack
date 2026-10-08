{% macro dh_clean_text(col) -%}
    nullif(btrim({{ col }}), '')
{%- endmacro %}

{% macro dh_safe_cast(expr, type) -%}
    case when pg_input_is_valid({{ expr }}, '{{ type }}') then ({{ expr }})::{{ type }} end
{%- endmacro %}

{% macro dh_to_int(col) -%}
    {{ dh_safe_cast(dh_clean_text(col), 'bigint') }}
{%- endmacro %}

{% macro dh_to_numeric(col, decimal='.') -%}
    {%- if decimal == ',' -%}
        {%- set expr = "replace(replace(" ~ dh_clean_text(col) ~ ", '.', ''), ',', '.')" -%}
    {%- else -%}
        {%- set expr = dh_clean_text(col) -%}
    {%- endif -%}
    {{ dh_safe_cast(expr, 'numeric') }}
{%- endmacro %}

{% macro dh_to_date(col, fmt='iso') -%}
    {%- if fmt == 'dmy' -%}
        {%- set expr = "regexp_replace(" ~ dh_clean_text(col) ~ ", '^(\\d{2})/(\\d{2})/(\\d{4})$', '\\3-\\2-\\1')" -%}
    {%- else -%}
        {%- set expr = "left(" ~ dh_clean_text(col) ~ ", 10)" -%}
    {%- endif -%}
    {{ dh_safe_cast(expr, 'date') }}
{%- endmacro %}

{% macro dh_to_timestamp(col) -%}
    {{ dh_safe_cast(dh_clean_text(col), 'timestamp') }}
{%- endmacro %}

{% macro dh_to_bool(col) -%}
    case
        when lower({{ dh_clean_text(col) }}) in ('true', 't', '1', 'sim', 's', 'yes', 'y') then true
        when lower({{ dh_clean_text(col) }}) in ('false', 'f', '0', 'nao', 'não', 'n', 'no') then false
    end
{%- endmacro %}
