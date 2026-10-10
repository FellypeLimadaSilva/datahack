param(
    [Parameter(Position = 0)][string]$Command = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Native = $env:DH_RUNNER -eq "native"
$ImagesTar = "images/datahack-images.tar"

function Import-DotEnv {
    if (-not (Test-Path ".env")) { throw "Arquivo .env ausente. Rode: .\scripts\dh.ps1 env" }
    foreach ($line in Get-Content ".env") {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }
}

function Invoke-CliCode {
    if ($Native) {
        Import-DotEnv
        $exe = $args[0]
        $tail = @($args | Select-Object -Skip 1)
        & $exe @tail | Out-Host
    } else {
        docker compose run --rm cli @args | Out-Host
    }
    return $LASTEXITCODE
}

function Invoke-Cli {
    $code = Invoke-CliCode @args
    if ($code -ne 0) { exit $code }
}

function Get-Python {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
    return $py
}

function Ensure-Env {
    $py = Get-Python
    if ($py) {
        & $py.Source scripts/init_env.py
    } elseif (Get-Command docker -ErrorAction SilentlyContinue) {
        docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim-bookworm python scripts/init_env.py
    } elseif (-not (Test-Path ".env")) {
        throw "Sem Python e sem Docker: nao ha como gerar o .env."
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Write-Check([string]$Name, [bool]$Ok, [string]$Fix, [bool]$Critical = $true, [string]$Info = "") {
    if ($Ok) { $tag = "[ OK ]"; $text = $Info } elseif ($Critical) { $tag = "[FALHA]"; $text = "$Info $Fix" } else { $tag = "[AVISO]"; $text = "$Info $Fix" }
    Write-Host ("{0} {1,-28} {2}" -f $tag, $Name, $text.Trim())
    return ($Ok -or -not $Critical)
}

function Test-Port([int]$Port) {
    if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) { return $true }
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return -not $busy
}

function Test-Native([scriptblock]$Command) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) } catch { return $false } finally { $ErrorActionPreference = $previous }
}

function Invoke-Doctor {
    $ok = $true
    $docker = [bool](Get-Command docker -ErrorAction SilentlyContinue)
    $ok = (Write-Check "Docker CLI" $docker "instale o Docker Desktop") -and $ok
    if ($docker) {
        $engine = Test-Native { docker info --format "{{.ServerVersion}}" }
        $ok = (Write-Check "Docker Engine" $engine "abra o Docker Desktop e aguarde 'Engine running'") -and $ok
        $compose = Test-Native { docker compose version }
        $ok = (Write-Check "Docker Compose v2" $compose "atualize o Docker Desktop") -and $ok
        if ($engine) {
            $mem = [double](docker info --format "{{.MemTotal}}") / 1GB
            $null = Write-Check "Memoria do Docker" ($mem -ge 3.5) "aumente em Settings > Resources (minimo 4 GB; 6 GB com Airflow)" $false ("{0:N1} GB" -f $mem)
        }
    }
    $wsl = Get-Command wsl -ErrorAction SilentlyContinue
    if ($wsl) {
        $wslOk = Test-Native { wsl --status }
        $null = Write-Check "WSL 2" $wslOk "se falhar: wsl --install (admin + reiniciar)" $false
    }
    $ok = (Write-Check "Git" ([bool](Get-Command git -ErrorAction SilentlyContinue)) "instale o Git") -and $ok
    $null = Write-Check "Python" ([bool](Get-Python)) "opcional; sem ele o .env e gerado via Docker" $false
    $drive = (Get-Location).Drive
    if ($drive) {
        $free = $drive.Free / 1GB
        $ok = (Write-Check "Disco livre" ($free -ge 10) "libere espaco (minimo 10 GB)" $true ("{0:N1} GB" -f $free)) -and $ok
    }
    $port = 5433
    if (Test-Path ".env") {
        $line = Select-String -Path ".env" -Pattern '^WAREHOUSE_PORT=(\d+)' | Select-Object -First 1
        if ($line) { $port = [int]$line.Matches[0].Groups[1].Value }
    }
    $null = Write-Check "Porta do banco ($port)" (Test-Port $port) "em uso: troque WAREHOUSE_PORT no .env" $false
    $null = Write-Check "Porta do Airflow (8080)" (Test-Port 8080) "em uso: troque AIRFLOW_PORT no .env" $false
    $null = Write-Check ".env" (Test-Path ".env") "rode: .\scripts\dh.ps1 env" $false
    $crlf = (Get-Content -Raw "infra/postgres/initdb/10-bootstrap.sh") -match "`r"
    $ok = (Write-Check "Fim de linha dos scripts" (-not $crlf) "clone de novo com: git config --global core.autocrlf false") -and $ok
    if ($ok) { Write-Host "Ambiente pronto." } else { Write-Host "Corrija os itens [FALHA] acima."; exit 1 }
}

function Invoke-NativeBootstrap {
    Import-DotEnv
    if (-not (Get-Command psql -ErrorAction SilentlyContinue)) { throw "psql nao encontrado: instale o PostgreSQL 16 e adicione o bin ao PATH." }
    $h = $env:WAREHOUSE_HOST; $p = $env:WAREHOUSE_PORT; $db = $env:WAREHOUSE_DB
    $exists = psql -h $h -p $p -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'"
    if ($exists -ne "1") { psql -h $h -p $p -U postgres -d postgres -c "CREATE DATABASE $db"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
    psql -v ON_ERROR_STOP=1 -h $h -p $p -U postgres -d $db `
        -v dbname=$db -v ingest_pw=$env:WAREHOUSE_INGEST_PASSWORD -v dbt_pw=$env:WAREHOUSE_DBT_PASSWORD `
        -v bi_pw=$env:WAREHOUSE_BI_PASSWORD -v backup_pw=$env:WAREHOUSE_BACKUP_PASSWORD `
        -f infra/postgres/bootstrap.sql
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Banco $db pronto em ${h}:$p"
}

switch ($Command) {
    "env"          { Ensure-Env }
    "doctor"       { Invoke-Doctor }
    "build"        { Ensure-Env; docker compose build }
    "up"           { Ensure-Env; docker compose up -d --build; Write-Host "Airflow: http://localhost:8080 | Postgres: localhost:5433" }
    "up-lite"      {
        Ensure-Env
        docker compose build cli; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        docker compose up -d --wait warehouse; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Invoke-Cli python -m datahack_ingest init
        Write-Host "Postgres pronto (sem Airflow). Use: .\scripts\dh.ps1 pipeline"
    }
    "down"         { docker compose down }
    "ps"           { docker compose ps }
    "logs"         { docker compose logs -f --tail=200 @Rest }
    "smoke"        {
        Invoke-Cli python -m datahack_ingest --version
        Invoke-Cli python -m datahack_ingest init
        Invoke-Cli python -m datahack_ingest validate
        Invoke-Cli dbt debug --project-dir dbt
        Write-Host "Smoke test concluido."
    }
    "images-save"  {
        New-Item -ItemType Directory -Force images | Out-Null
        $images = docker compose --profile cli config --images | Sort-Object -Unique
        $present = @($images | Where-Object { $name = $_; Test-Native { docker image inspect $name } })
        if (-not $present) { throw "Nenhuma imagem local. Rode antes: .\scripts\dh.ps1 up-lite (ou build)" }
        docker save -o $ImagesTar @present; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host ("Salvo {0} ({1}) em {2}" -f ($present -join ", "), ("{0:N0} MB" -f ((Get-Item $ImagesTar).Length / 1MB)), $ImagesTar)
    }
    "images-load"  {
        if (-not (Test-Path $ImagesTar)) { throw "Copie o arquivo para $ImagesTar antes." }
        docker load -i $ImagesTar; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    "db-bootstrap-native" { Invoke-NativeBootstrap }
    "import-downloads" {
        $from = if ($Rest) { $Rest[0] } else { Join-Path $HOME "Downloads" }
        $rules = @(
            @{ Pattern = "microdados_censo_da_educacao_superior_*.zip"; Dest = "data/landing/inep/censo" },
            @{ Pattern = "indicadores_trajetoria_es_*.zip"; Dest = "data/landing/inep/trajetoria" },
            @{ Pattern = "cpc_*.xlsx"; Dest = "data/landing/inep/qualidade" },
            @{ Pattern = "igc_*.xlsx"; Dest = "data/landing/inep/qualidade" },
            @{ Pattern = "conceito_enade_licenciaturas*.xlsx"; Dest = "data/landing/inep/qualidade" }
        )
        foreach ($rule in $rules) {
            New-Item -ItemType Directory -Force $rule.Dest | Out-Null
            $found = @(Get-ChildItem -Path $from -Filter $rule.Pattern -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notmatch "\(\d+\)" })
            foreach ($file in $found) {
                Copy-Item $file.FullName -Destination $rule.Dest -Force
                Write-Host ("[copiado] {0} -> {1}" -f $file.Name, $rule.Dest)
            }
            if (-not $found) { Write-Host ("[faltando] {0}" -f $rule.Pattern) }
        }
    }
    "ingest"       { if ($Rest) { Invoke-Cli python -m datahack_ingest run @Rest } else { Invoke-Cli python -m datahack_ingest run --all --continue-on-error } }
    "gate"         { Invoke-Cli python -m datahack_ingest gate }
    "dbt-build"    { if ($Rest) { Invoke-Cli dbt build --project-dir dbt --select @Rest } else { Invoke-Cli dbt build --project-dir dbt } }
    "dbt-test"     { Invoke-Cli dbt test --project-dir dbt }
    "publish"      { Invoke-Cli python -m datahack_ingest publish }
    "rollback"     { Invoke-Cli python -m datahack_ingest rollback }
    "export"       { Invoke-Cli python -m datahack_ingest export @Rest }
    "pipeline"     { Invoke-Cli python -m datahack_ingest pipeline @Rest }
    "dashboard"    {
        $py = Get-Python
        if ($py -and (Test-Native { & $py.Source -c "import streamlit" })) {
            & $py.Source -m streamlit run dashboard/app.py
        } elseif (Get-Command docker -ErrorAction SilentlyContinue) {
            Write-Host "Instalando o Streamlit no container (1 a 2 minutos na primeira vez)."
            Write-Host "Abra http://localhost:8501 quando aparecer 'You can now view your Streamlit app'. Ctrl+C encerra."
            docker run --rm -it -p 127.0.0.1:8501:8501 -v "${PWD}:/w" -w /w python:3.12-slim-bookworm `
                bash -c "pip install -q -r dashboard/requirements.txt && streamlit run dashboard/app.py --server.address 0.0.0.0 --server.headless true"
        } else {
            throw "Instale o Python 3.12 e rode: pip install -r dashboard/requirements.txt"
        }
    }
    "psql"         { docker compose exec warehouse bash -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB' }
    "backup"       { docker compose run --rm -e BACKUP_ONCE=true warehouse-backup }
    "db-bootstrap" { docker compose exec warehouse bash /docker-entrypoint-initdb.d/10-bootstrap.sh }
    "test"         { pytest -q }
    "lint"         { ruff check .; ruff format --check .; sqlfluff lint dbt/models }
    "nuke" {
        $ans = Read-Host "Apagar TODOS os volumes (dados do warehouse)? digite 'sim'"
        if ($ans -eq "sim") { docker compose down -v }
    }
    default {
        Write-Host @"
Uso: .\scripts\dh.ps1 <comando> [args]      (sem Docker: `$env:DH_RUNNER = "native")
  doctor                      verifica Docker, WSL, disco, portas e fim de linha
  env                         cria ou completa o .env
  up-lite                     sobe so o Postgres e a imagem CLI (recomendado no laboratorio)
  up | build | down | ps | logs [servico]   plataforma completa com Airflow
  smoke                       testa CLI, banco e dbt
  images-save | images-load   leva as imagens num pendrive (images/datahack-images.tar)
  db-bootstrap-native         prepara um PostgreSQL instalado sem Docker
  import-downloads [pasta]    copia os arquivos do INEP de Downloads para data\landing\inep
  pipeline                    ingestao + portao + dbt em gold_candidate + publicacao + outputs/
  ingest [fontes...]          so a ingestao na Bronze
  gate                        mostra se as fontes obrigatorias estao completas
  dbt-build [seletor]         dbt build no schema candidato (nao publica)
  publish | rollback          promove o candidato / volta a versao anterior
  export [--tables ...]       exporta a Gold publicada para outputs/
  dashboard                   abre o dashboard lendo outputs/
  dbt-test | psql | db-bootstrap | backup | test | lint | nuke
"@
    }
}
