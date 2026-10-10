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

{% macro dh_mask_count(expr) -%}
    case when ({{ expr }}) between 1 and {{ var('min_cell') }} - 1 then null else ({{ expr }}) end
{%- endmacro %}

{% macro dh_rate(numerator, denominator, scale=100) -%}
    round(({{ scale }} * ({{ numerator }})::numeric / nullif({{ denominator }}, 0))::numeric, 2)
{%- endmacro %}

{% macro dh_rede(categoria) -%}
    case
        when {{ categoria }} in (1, 2, 3, 7) then 'Pública'
        when {{ categoria }} in (4, 5, 6) then 'Privada'
    end
{%- endmacro %}

{% macro dh_modalidade(code) -%}
    case {{ code }} when 1 then 'Presencial' when 2 then 'EAD' end
{%- endmacro %}

{% macro dh_grau(code) -%}
    case {{ code }}
        when 1 then 'Bacharelado'
        when 2 then 'Licenciatura'
        when 3 then 'Tecnológico'
        when 4 then 'Bacharelado e Licenciatura'
    end
{%- endmacro %}

{% macro dh_latest_partition(relation, partition) -%}
    select r.*
    from {{ relation }} as r
    inner join (
        select distinct on (btrim({{ partition }}))
            btrim({{ partition }}) as _dh_particao,
            _dh_source_file as _dh_arquivo,
            _dh_batch_id as _dh_lote
        from {{ relation }}
        where nullif(btrim({{ partition }}), '') is not null
        order by btrim({{ partition }}), _dh_ingested_at desc
    ) as v
        on btrim(r.{{ partition }}) = v._dh_particao
        and r._dh_source_file = v._dh_arquivo
        and r._dh_batch_id = v._dh_lote
{%- endmacro %}

{% macro dh_relation_exists(source_name, table_name) -%}
    {%- if not execute -%}
        {{ return(true) }}
    {%- endif -%}
    {%- set src = source(source_name, table_name) -%}
    {%- set rel = adapter.get_relation(database=src.database, schema=src.schema, identifier=src.identifier) -%}
    {{ return(rel is not none) }}
{%- endmacro %}

{% macro dh_pick_column(source_name, table_name, patterns) -%}
    {%- if not execute -%}
        {{ return(none) }}
    {%- endif -%}
    {%- set src = source(source_name, table_name) -%}
    {%- set rel = adapter.get_relation(database=src.database, schema=src.schema, identifier=src.identifier) -%}
    {%- if rel is none -%}
        {{ return(none) }}
    {%- endif -%}
    {%- set names = adapter.get_columns_in_relation(rel) | map(attribute='name') | list -%}
    {%- for pattern in patterns -%}
        {%- for name in names -%}
            {%- if modules.re.search(pattern, name) -%}
                {{ return(name) }}
            {%- endif -%}
        {%- endfor -%}
    {%- endfor -%}
    {{ return(none) }}
{%- endmacro %}
