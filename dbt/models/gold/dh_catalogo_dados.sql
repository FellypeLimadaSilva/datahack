{{ config(contract={'enforced': true}) }}

select
    c.table_name::text                                 as tabela_bronze,
    m.source::text                                     as fonte,
    ('silver.' || m.silver_alias)::text                as tabela_silver,
    ('gold.' || m.gold_alias)::text                    as tabela_gold,
    c.column_name::text                                as coluna_origem,
    c.output_name::text                                as coluna,
    c.ordinal::integer                                 as ordem,
    c.inferred_type::text                              as tipo,
    c.type_format::text                                as formato,
    coalesce(c.pii_class, 'nenhum')::text              as classificacao_lgpd,
    (c.pii_class is not distinct from 'identificador') as is_pseudonimizada,
    c.is_key::boolean                                  as is_chave,
    m.dedup::text                                      as deduplicacao,
    m.materialization::text                            as materializacao,
    c.valid_ratio::numeric                             as taxa_validos_amostra,
    c.null_ratio::numeric                              as taxa_nulos_amostra,
    c.distinct_ratio::numeric                          as taxa_distintos_amostra,
    c.max_length::integer                              as tamanho_maximo,
    c.sample_rows::bigint                              as linhas_amostra,
    m.row_count::bigint                                as linhas_bronze,
    c.profiled_at::timestamptz                         as perfilado_em,
    m.generated_at::timestamptz                        as gerado_em
from {{ source('ops', 'data_catalog') }} as c
inner join {{ source('ops', 'auto_models') }} as m using (table_name)
