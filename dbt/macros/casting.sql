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
    {%- set stripped = "regexp_replace(" ~ dh_clean_text(col) ~ ", '(R\\$|\\s)', '', 'g')" -%}
    {%- if decimal == ',' -%}
        {%- set expr = "replace(replace(" ~ stripped ~ ", '.', ''), ',', '.')" -%}
    {%- elif decimal == 'auto' -%}
        {%- set expr = "case when " ~ stripped ~ " like '%,%' then replace(replace(" ~ stripped ~ ", '.', ''), ',', '.') else " ~ stripped ~ " end" -%}
    {%- else -%}
        {%- set expr = stripped -%}
    {%- endif -%}
    {{ dh_safe_cast(expr, 'numeric') }}
{%- endmacro %}

{% macro dh_to_date(col, fmt='iso') -%}
    {%- set pattern = "'^(\\d{1,2})[/.-](\\d{1,2})[/.-](\\d{4})$'" -%}
    {%- if fmt == 'dmy' -%}
        {%- set expr = "regexp_replace(" ~ dh_clean_text(col) ~ ", " ~ pattern ~ ", '\\3-\\2-\\1')" -%}
    {%- elif fmt == 'mdy' -%}
        {%- set expr = "regexp_replace(" ~ dh_clean_text(col) ~ ", " ~ pattern ~ ", '\\3-\\1-\\2')" -%}
    {%- else -%}
        {%- set expr = "left(" ~ dh_clean_text(col) ~ ", 10)" -%}
    {%- endif -%}
    {{ dh_safe_cast(expr, 'date') }}
{%- endmacro %}

{% macro dh_to_timestamp(col, fmt='iso', tz=false) -%}
    {%- set target = 'timestamptz' if tz else 'timestamp' -%}
    {%- if fmt == 'dmy' -%}
        {%- set pattern = "'^(\\d{1,2})[/.-](\\d{1,2})[/.-](\\d{4})[ T](.+)$'" -%}
        {%- set expr = "regexp_replace(" ~ dh_clean_text(col) ~ ", " ~ pattern ~ ", '\\3-\\2-\\1 \\4')" -%}
    {%- else -%}
        {%- set expr = dh_clean_text(col) -%}
    {%- endif -%}
    {{ dh_safe_cast(expr, target) }}
{%- endmacro %}

{% macro dh_to_bool(col) -%}
    case
        when lower({{ dh_clean_text(col) }}) in ('true', 't', '1', 'sim', 's', 'yes', 'y') then true
        when lower({{ dh_clean_text(col) }}) in ('false', 'f', '0', 'nao', 'não', 'n', 'no') then false
    end
{%- endmacro %}

{% macro dh_to_jsonb(col) -%}
    {{ dh_safe_cast(dh_clean_text(col), 'jsonb') }}
{%- endmacro %}
