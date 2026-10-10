# Sobe o Superset da Rota do Diploma.
#   Modo normal  (lê o schema gold do warehouse):   powershell -ExecutionPolicy Bypass -File .\up.ps1
#   PLANO B      (sem banco, lê planilhas):          powershell -ExecutionPolicy Bypass -File .\up.ps1 -Planilhas
# O modo normal lê as variaveis do .env da raiz do repositorio e grava superset\.env (fora do Git).
# O Plano B nao precisa do warehouse nem do .env da raiz: so do Docker. Os dois modos usam a mesma porta
# (SUPERSET_PORT do superset\.env, padrao 8088): subir um para o outro, e o chat com IA (se ja existe) troca junto.
param([switch]$Planilhas)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$rootEnv = Join-Path $here "..\.env"
$ownEnv = Join-Path $here ".env"

function Read-DotEnv([string]$Path) {
    $map = @{}
    if (Test-Path $Path) {
        foreach ($line in Get-Content $Path) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') { $map[$Matches[1]] = $Matches[2].Trim('"') }
        }
    }
    return $map
}
function New-Secret([int]$Bytes) {
    $b = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return ([Convert]::ToBase64String($b) -replace '[^A-Za-z0-9]', '').Substring(0, [Math]::Min($Bytes, 40))
}
function Write-DotEnv($Map) {
    ($Map.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) | Set-Content -Path $ownEnv -Encoding ascii
}
function Dk {   # docker "silencioso": no Windows PowerShell 5.1 o stderr de um exe nativo viraria erro fatal
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & docker @args 2>$null } finally { $ErrorActionPreference = $old }
}
function Test-DockerUp {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & docker info 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } finally { $ErrorActionPreference = $old }
}
function Switch-Chat([bool]$Plano) {
    # O chat com IA tem de ler da mesma fonte que o Superset. So mexe nele se ja foi criado antes (chatbot\up.ps1).
    $dir = Join-Path $here "..\chatbot"
    if (-not (Test-Path (Join-Path $dir ".env"))) { return }
    if (-not (Dk ps -a --filter "name=rota-chatbot-chatbot-1" --format "{{.Names}}")) { return }
    $emPlano = (Dk inspect rota-chatbot-chatbot-1 --format "{{range .Config.Env}}{{println .}}{{end}}") -contains "DATA_SOURCE=planilhas"
    if ($emPlano -eq $Plano) { return }
    $files = @("-f", "docker-compose.yml"); if ($Plano) { $files += @("-f", "docker-compose.planilhas.yml") }
    Push-Location $dir
    try {
        Write-Host "Trocando o chat com IA para a mesma fonte ($(if ($Plano) { 'planilhas' } else { 'warehouse' }))..."
        docker compose @files up -d --build
        if ($LASTEXITCODE -ne 0) { Write-Host "AVISO: nao consegui trocar o chat (codigo $LASTEXITCODE). O dashboard funciona; rode chatbot\up.ps1." -ForegroundColor Yellow }
    } finally { Pop-Location }
}
function Get-Endereco($Own) {
    # se o gateway (porta unica) esta de pe, e ele o endereco de uso
    if (Dk ps --filter "name=rota-gateway-gateway-1" --format "{{.Names}}") { return "http://localhost:8088  (via gateway; Superset em $(if ($Own['SUPERSET_PORT']) { $Own['SUPERSET_PORT'] } else { '8088' }))" }
    return "http://localhost:$(if ($Own['SUPERSET_PORT']) { $Own['SUPERSET_PORT'] } else { '8088' })"
}

$own = Read-DotEnv $ownEnv
if (-not $own["SUPERSET_SECRET_KEY"])     { $own["SUPERSET_SECRET_KEY"]     = (New-Secret 48) + (New-Secret 48) }
if (-not $own["SUPERSET_ADMIN_PASSWORD"]) { $own["SUPERSET_ADMIN_PASSWORD"] = New-Secret 20 }

if ($Planilhas) {
    # ---------- PLANO B: sem banco de dados ----------
    Write-DotEnv $own
    if (-not (Test-DockerUp)) { throw "O Docker nao esta rodando. Abra o Docker Desktop e tente de novo." }
    Push-Location $here
    try {
        Dk compose -p rota-superset stop superset | Out-Null      # mesma porta do modo normal: para o outro (os dados dele ficam guardados)
        docker compose -f docker-compose.planilhas.yml up -d --build
        if ($LASTEXITCODE -ne 0) { throw "docker compose falhou (codigo $LASTEXITCODE)" }
    } finally { Pop-Location }
    Switch-Chat $true
    Write-Host ""
    Write-Host "PLANO B (planilhas) no ar: $(Get-Endereco $own)   usuario: admin   senha: $($own['SUPERSET_ADMIN_PASSWORD'])"
    Write-Host "Solte as planilhas em superset\planilhas\ (csv, xlsx, xls, ods, parquet, json...): o painel atualiza sozinho em ~10 s."
    Write-Host "Sem nada la, ele usa as exportacoes da Gold em outputs\. Para ver o que foi lido:"
    Write-Host "  docker compose -f superset/docker-compose.planilhas.yml exec superset python /app/planilhas.py --check"
    return
}

# ---------- Modo normal: warehouse ----------
if (-not (Test-Path $rootEnv)) { throw "Nao achei o .env da raiz. Rode antes: .\scripts\dh.ps1 env  (ou up-lite). Sem banco? Use: .\up.ps1 -Planilhas" }
$root = Read-DotEnv $rootEnv
if (-not $root["WAREHOUSE_BI_PASSWORD"] -or $root["WAREHOUSE_BI_PASSWORD"] -eq "__GERAR__") { throw "WAREHOUSE_BI_PASSWORD ausente no .env da raiz." }

$project = if ($root["COMPOSE_PROJECT_NAME"]) { $root["COMPOSE_PROJECT_NAME"] } else { "datahack" }
$own["WAREHOUSE_NETWORK"]     = "${project}_warehouse"
$own["WAREHOUSE_DB"]          = if ($root["WAREHOUSE_DB"]) { $root["WAREHOUSE_DB"] } else { "datahack" }
$own["WAREHOUSE_BI_USER"]     = if ($root["WAREHOUSE_BI_USER"]) { $root["WAREHOUSE_BI_USER"] } else { "dh_bi_reader" }
$own["WAREHOUSE_BI_PASSWORD"] = $root["WAREHOUSE_BI_PASSWORD"]
Write-DotEnv $own

if (-not (docker network ls --format '{{.Name}}' | Select-String -SimpleMatch -Quiet $own["WAREHOUSE_NETWORK"])) {
    throw "Rede $($own['WAREHOUSE_NETWORK']) nao existe. Suba o warehouse antes: .\scripts\dh.ps1 up-lite   (ou use o Plano B: .\up.ps1 -Planilhas)"
}
Push-Location $here
try {
    Dk compose -f docker-compose.planilhas.yml stop superset | Out-Null     # libera a porta se o Plano B estava de pe
    docker compose up -d --build; if ($LASTEXITCODE -ne 0) { throw "docker compose falhou (codigo $LASTEXITCODE)" }
} finally { Pop-Location }
Switch-Chat $false
Write-Host ""
Write-Host "Superset: $(Get-Endereco $own)   usuario: admin   senha: $($own['SUPERSET_ADMIN_PASSWORD'])"
Write-Host "Leitura sem login esta liberada. A primeira abertura demora (importa o dashboard)."
