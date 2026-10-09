{{ config(contract={'enforced': true}) }}

select
    loja_id::bigint         as loja_id,
    nome_loja::text         as nome_loja,
    cidade::text            as cidade,
    uf::text                as uf,
    regiao::text            as regiao,
    data_inauguracao::date  as data_inauguracao,
    data_fechamento::date   as data_fechamento,
    area_m2::numeric(12, 2) as area_m2,
    (
        data_fechamento is null
        or data_fechamento >= current_date
    )::boolean              as is_ativa
from {{ ref('stg_lojas') }}
