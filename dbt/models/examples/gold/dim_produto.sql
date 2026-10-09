{{ config(contract={'enforced': true}) }}

select
    produto_id::bigint          as produto_id,
    sku::text                   as sku,
    nome_produto::text          as nome_produto,
    departamento::text          as departamento,
    categoria::text             as categoria,
    preco_lista::numeric(18, 2) as preco_lista,
    is_ativo::boolean           as is_ativo,
    is_promocional::boolean     as is_promocional
from {{ ref('stg_produtos') }}
