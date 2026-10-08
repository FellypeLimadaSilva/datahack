param(
    [Parameter(Position = 0)][string]$Command = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Cli { docker compose run --rm cli @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
function Ensure-Env {
    if (-not (Test-Path ".env")) {
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
        if (-not $py) { throw "Python nao encontrado. Instale Python 3.12+ ou rode via devcontainer." }
        & $py.Source scripts/init_env.py
    }
}

switch ($Command) {
    "env"          { Ensure-Env }
    "build"        { Ensure-Env; docker compose build }
    "up"           { Ensure-Env; docker compose up -d --build; Write-Host "Airflow: http://localhost:8080 | Postgres: localhost:5433" }
    "down"         { docker compose down }
    "ps"           { docker compose ps }
    "logs"         { docker compose logs -f --tail=200 @Rest }
    "sample"       { Invoke-Cli python scripts/generate_sample_data.py --out data/landing/sample }
    "ingest"       { if ($Rest) { Invoke-Cli python -m datahack_ingest run @Rest } else { Invoke-Cli python -m datahack_ingest run --all } }
    "dbt-build"    { if ($Rest) { Invoke-Cli dbt build --project-dir dbt --select @Rest } else { Invoke-Cli dbt build --project-dir dbt } }
    "dbt-test"     { Invoke-Cli dbt test --project-dir dbt }
    "pipeline"     { & $PSCommandPath ingest; & $PSCommandPath dbt-build }
    "psql"         { docker compose exec warehouse bash -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB' }
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
  sample                      gera dataset de exemplo
  ingest [fontes...]          ingere fontes (padrao: todas habilitadas)
  dbt-build [seletor]         dbt build (models + testes)
  dbt-test | pipeline | psql | db-bootstrap | test | lint | nuke
"@
    }
}
