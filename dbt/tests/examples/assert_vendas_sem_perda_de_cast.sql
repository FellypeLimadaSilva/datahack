{{ config(severity='warn') }}

select b.venda_id, b.item_seq, b.quantidade, b.valor_unitario, b.data_hora_venda
from {{ source('bronze', 'vendas') }} b
join {{ ref('stg_vendas') }} s
  on s.venda_id::text = b.venda_id and s.item_seq::text = b.item_seq
where (nullif(btrim(b.quantidade), '') is not null and s.quantidade is null)
   or (nullif(btrim(b.valor_unitario), '') is not null and s.valor_unitario is null)
   or (nullif(btrim(b.data_hora_venda), '') is not null and s.data_hora_venda is null)
