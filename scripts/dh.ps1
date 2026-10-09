param(
    [Parameter(Position = 0)][string]$Command = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Cli { docker compose run --rm cli @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
function Ensure-Env {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $py) {
        if (Test-Path ".env") { return }
        throw "Python nao encontrado. Instale Python 3.12+ ou rode via devcontainer."
    }
    & $py.Source scripts/init_env.py
}

switch ($Command) {
    "env"          { Ensure-Env }
    "build"        { Ensure-Env; docker compose build }
    "up"           { Ensure-Env; docker compose up -d --build; Write-Host "Airflow: http://localhost:8080 | Postgres: localhost:5433" }
    "down"         { docker compose down }
    "ps"           { docker compose ps }
    "logs"         { docker compose logs -f --tail=200 @Rest }
    "sample"       { Invoke-Cli python scripts/generate_sample_data.py --out data/landing/sample }
    "demo-inbox"   { Invoke-Cli python scripts/generate_messy_data.py --out data/landing/inbox }
    "discover"     { Invoke-Cli python -m datahack_ingest discover }
    "ingest"       { if ($Rest) { Invoke-Cli python -m datahack_ingest run @Rest } else { Invoke-Cli python -m datahack_ingest run --all --continue-on-error } }
    "models"       { Invoke-Cli python -m datahack_ingest generate-models @Rest }
    "dbt-build"    { if ($Rest) { Invoke-Cli dbt build --project-dir dbt --select @Rest } else { Invoke-Cli dbt build --project-dir dbt } }
    "dbt-test"     { Invoke-Cli dbt test --project-dir dbt }
    "pipeline" {
        docker compose run --rm cli python -m datahack_ingest run --all --continue-on-error
        $ingest = $LASTEXITCODE
        if ($ingest -ne 0 -and $env:DH_REQUIRE_ALL_SOURCES -eq "true") { exit $ingest }
        Invoke-Cli python -m datahack_ingest generate-models
        Invoke-Cli dbt build --project-dir dbt
        if ($ingest -ne 0) { Write-Host "Atencao: fontes com falha na ingestao (veja o JSON acima)."; exit $ingest }
    }
    "psql"         { docker compose exec warehouse bash -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB' }
    "backup"       { docker compose run --rm -e BACKUP_ONCE=true warehouse-backup }
    "ha-up"        { docker compose --profile ha up -d warehouse-replica }
    "alert-test"   { Invoke-Cli python -m datahack_ingest alert-test }
    "db-bootstrap" { docker compose exec warehouse bash /docker-entrypoint-initdb.d/10-bootstrap.sh }
    "test"         { pytest -q }
    "lint"         { ruff check .; ruff format --check .; sqlfluff lint dbt/models }
    "nuke" {
        $ans = Read-Host "Apagar TODOS os volumes (dados do warehouse)? digite 'sim'"
        if ($ans -eq "sim") { docker compose down -v }
    }
    default {
        Write-Host @"
Uso: .\scripts\dh.ps1 <comando> [args]
  env | build | up | down | ps | logs [servico]
  sample                      gera dataset de exemplo (varejo)
  demo-inbox                  gera arquivos baguncados em data/landing/inbox
  discover                    mostra o que a inbox virou de fonte e o que foi ignorado
  ingest [fontes...]          ingere fontes (padrao: todas, continuando em caso de erro)
  models [--reset]            gera Silver e Gold automaticas a partir da Bronze
  dbt-build [seletor]         dbt build (models + testes)
  pipeline                    ingest + models + dbt-build
  dbt-test | psql | db-bootstrap | backup | ha-up | alert-test | test | lint | nuke
"@
    }
}
