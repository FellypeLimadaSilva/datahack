{{ config(contract={'enforced': true}) }}

with ultima as (
    select distinct on (source)
        source,
        status,
        started_at,
        finished_at,
        rows_loaded,
        rows_rejected,
        error
    from {{ source('ops', 'ingestion_runs') }}
    order by source asc, started_at desc
),

ultimo_sucesso as (
    select
        source,
        max(finished_at) as finished_at
    from {{ source('ops', 'ingestion_runs') }}
    where status = 'success'
    group by source
),

arquivos as (
    select
        source,
        count(*) as nu_arquivos,
        sum(rows_loaded) as linhas
    from {{ source('ops', 'file_manifest') }}
    group by source
),

ultima_carga_full as (
    select distinct on (source)
        source,
        rows_loaded
    from {{ source('ops', 'ingestion_runs') }}
    where status = 'success' and rows_loaded > 0
    order by source asc, started_at desc
)

select
    u.source::text as fonte,
    u.status::text as ultimo_status,
    (s.finished_at at time zone '{{ var("timezone") }}')::timestamp as ultima_carga_sucesso_local,
    s.finished_at::timestamptz as ultima_carga_sucesso_utc,
    u.rows_loaded::bigint as linhas_ultima_execucao,
    u.rows_rejected::bigint as linhas_rejeitadas_ultima_execucao,
    coalesce(a.nu_arquivos, 0)::bigint as nu_arquivos_carregados,
    coalesce(a.linhas, f.rows_loaded, 0)::bigint as linhas_disponiveis,
    ('{{ run_started_at }}'::timestamptz at time zone '{{ var("timezone") }}')::timestamp
        as ultima_transformacao_local,
    '{{ var("timezone") }}'::text as fuso_horario
from ultima as u
left join ultimo_sucesso as s on u.source = s.source
left join arquivos as a on u.source = a.source
left join ultima_carga_full as f on u.source = f.source
