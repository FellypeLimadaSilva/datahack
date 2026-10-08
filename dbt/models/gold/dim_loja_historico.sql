select
    dbt_scd_id::text                   as loja_versao_id,
    loja_id::bigint                    as loja_id,
    nome_loja::text                    as nome_loja,
    cidade::text                       as cidade,
    uf::text                           as uf,
    regiao::text                       as regiao,
    data_inauguracao::date             as data_inauguracao,
    data_fechamento::date              as data_fechamento,
    area_m2::numeric(12, 2)            as area_m2,
    dbt_valid_from::timestamp          as valido_de,
    dbt_valid_to::timestamp            as valido_ate,
    (dbt_valid_to is null)::boolean    as is_atual
from {{ ref('snap_lojas') }}
