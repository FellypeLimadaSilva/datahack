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

{% macro dh_typed_column(name, kind='text') -%}
    {%- if name is none -%}
        null::{{ kind }}
    {%- elif kind == 'numeric' -%}
        {{ dh_to_numeric(name, 'auto') }}::numeric
    {%- elif kind in ('bigint', 'int') -%}
        {{ dh_to_int(name) }}::{{ kind }}
    {%- else -%}
        {{ dh_clean_text(name) }}::text
    {%- endif -%}
{%- endmacro %}
