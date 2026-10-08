select
    dbt_scd_id::text                   as produto_versao_id,
    produto_id::bigint                 as produto_id,
    sku::text                          as sku,
    nome_produto::text                 as nome_produto,
    departamento::text                 as departamento,
    categoria::text                    as categoria,
    preco_lista::numeric(18, 2)        as preco_lista,
    is_ativo::boolean                  as is_ativo,
    is_promocional::boolean            as is_promocional,
    dbt_valid_from::timestamp          as valido_de,
    dbt_valid_to::timestamp            as valido_ate,
    (dbt_valid_to is null)::boolean    as is_atual
from {{ ref('snap_produtos') }}
