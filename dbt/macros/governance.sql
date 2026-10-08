{% macro dh_hash_pii(col, digits_only=false) -%}
    {%- if digits_only -%}
        {%- set normalized = "regexp_replace(" ~ col ~ ", '\\D', '', 'g')" -%}
    {%- else -%}
        {%- set normalized = "lower(btrim(" ~ col ~ "))" -%}
    {%- endif -%}
    case
        when {{ dh_clean_text(col) }} is null then null
        else encode(sha256(convert_to('{{ env_var("DBT_PII_SALT", "") }}' || {{ normalized }}, 'UTF8')), 'hex')
    end
{%- endmacro %}

{% macro dh_latest(relation, keys, order_by='_dh_ingested_at desc', include_deleted=false) -%}
    select * from (
        select
            r.*,
            row_number() over (partition by {{ keys | join(', ') }} order by {{ order_by }}) as _dh_rn
        from {{ relation }} r
    ) ranked
    where _dh_rn = 1
    {%- if not include_deleted %}
      and _dh_deleted_at is null
    {%- endif %}
{%- endmacro %}

{% macro dh_easter_sunday(year) -%}
    (
        with p as (select ({{ year }})::int as y),
        s1 as (
            select y, y % 19 as a, y / 100 as b, y % 100 as c from p
        ),
        s2 as (
            select y, a, b, c, b / 4 as d, b % 4 as e, (b + 8) / 25 as f, c / 4 as i, c % 4 as k
            from s1
        ),
        s3 as (
            select y, a, i, k, e,
                   (19 * a + b - d - ((b - f + 1) / 3) + 15) % 30 as h
            from s2
        ),
        s4 as (
            select y, a, h, (32 + 2 * e + 2 * i - h - k) % 7 as l from s3
        ),
        s5 as (
            select y, h, l, (a + 11 * h + 22 * l) / 451 as m from s4
        )
        select make_date(y, (h + l - 7 * m + 114) / 31, ((h + l - 7 * m + 114) % 31) + 1) from s5
    )
{%- endmacro %}
