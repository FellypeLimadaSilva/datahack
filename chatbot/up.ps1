# Sobe o chat com IA (DeepSeek) do dashboard, lendo a camada gold com o papel dh_bi_reader.
# Lê o .env da raiz do repositorio e grava chatbot\.env (fora do Git).
# Nada para configurar aqui: a chave da DeepSeek e informada no navegador (Settings > Configuracoes do chat (IA)).
#   powershell -ExecutionPolicy Bypass -File .\up.ps1
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

if (-not (Test-Path $rootEnv)) { throw "Nao achei o .env da raiz. Rode antes: .\scripts\dh.ps1 env  (ou up-lite)." }
$root = Read-DotEnv $rootEnv
if (-not $root["WAREHOUSE_BI_PASSWORD"] -or $root["WAREHOUSE_BI_PASSWORD"] -eq "__GERAR__") { throw "WAREHOUSE_BI_PASSWORD ausente no .env da raiz." }

$own = @{}   # arquivo gerado do zero a cada subida: so a conexao com o banco, nada de chaves
$project = if ($root["COMPOSE_PROJECT_NAME"]) { $root["COMPOSE_PROJECT_NAME"] } else { "datahack" }
$own["WAREHOUSE_NETWORK"]     = "${project}_warehouse"
$own["WAREHOUSE_DB"]          = if ($root["WAREHOUSE_DB"]) { $root["WAREHOUSE_DB"] } else { "datahack" }
$own["WAREHOUSE_BI_USER"]     = if ($root["WAREHOUSE_BI_USER"]) { $root["WAREHOUSE_BI_USER"] } else { "dh_bi_reader" }
$own["WAREHOUSE_BI_PASSWORD"] = $root["WAREHOUSE_BI_PASSWORD"]

($own.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) | Set-Content -Path $ownEnv -Encoding ascii

if (-not (docker network ls --format '{{.Name}}' | Select-String -SimpleMatch -Quiet $own["WAREHOUSE_NETWORK"])) {
    throw "Rede $($own['WAREHOUSE_NETWORK']) nao existe. Suba o warehouse antes: .\scripts\dh.ps1 up-lite"
}
Push-Location $here
try { docker compose up -d --build; if ($LASTEXITCODE -ne 0) { throw "docker compose falhou (codigo $LASTEXITCODE)" } } finally { Pop-Location }
Write-Host ""
Write-Host "Chat no ar. Abra o sistema pelo endereco unico (gateway\up.ps1) e informe a chave da DeepSeek em Settings > Configuracoes do chat (IA)."
