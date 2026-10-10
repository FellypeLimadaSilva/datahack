# Porta única do sistema: http://localhost:8088 abre o dashboard e, nele, o chat com IA (botão "Pergunte aos dados").
# Suba antes o Superset (superset\up.ps1) e o chat (chatbot\up.ps1). Este script:
#   1. libera a porta 8088 movendo o Superset para outra porta (ele continua acessível só como apoio);
#   2. sobe o nginx na 8088, que serve o Superset em / e o chat em /assistente/.
#   powershell -ExecutionPolicy Bypass -File .\up.ps1
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$gatewayPort = if ($env:GATEWAY_PORT) { [int]$env:GATEWAY_PORT } else { 8088 }

function Dk {   # docker sem que o stderr vire erro no Windows PowerShell 5.1
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & docker @args 2>$null } finally { $ErrorActionPreference = $old }
}
function Get-HostPort([string]$Container, [string]$Inner) {
    $line = Dk port $Container $Inner | Select-Object -First 1
    if ($line -and $line -match ':(\d+)\s*$') { return [int]$Matches[1] }
    return $null
}
function Find-FreePort([int]$From) {
    foreach ($p in $From..($From + 20)) {
        $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $p)
        try { $l.Start(); $l.Stop(); return $p } catch { }
    }
    throw "Nenhuma porta livre a partir de $From."
}
function Wait-Health([string]$Container) {
    foreach ($i in 1..60) {
        $s = Dk inspect -f "{{.State.Health.Status}}" $Container
        if ($s -eq "healthy") { return }
        Start-Sleep -Seconds 3
    }
}

$whName = "rota-superset-superset-1"; $plName = "rota-superset-planilhas-superset-1"; $chatName = "rota-chatbot-chatbot-1"
$whPort = Get-HostPort $whName "8088/tcp"
$plPort = Get-HostPort $plName "8088/tcp"
if (-not $whPort -and -not $plPort) { throw "O Superset nao esta no ar. Rode antes: superset\up.ps1" }
$usePlanilhas = (-not $whPort)
$supersetPort = if ($usePlanilhas) { $plPort } else { $whPort }

if ($supersetPort -eq $gatewayPort) {
    $novo = Find-FreePort 8090
    Write-Host "O Superset esta na $gatewayPort; movendo para $novo para a porta $gatewayPort ser a unica porta de uso..."
    Push-Location (Join-Path $here "..\superset")
    try {
        if ($usePlanilhas) {
            $env:SUPERSET_PORT = "$novo"
            docker compose -f docker-compose.planilhas.yml up -d
        } else {
            $envFile = Join-Path (Get-Location) ".env"
            $lines = if (Test-Path $envFile) { @(Get-Content $envFile) } else { @() }
            $lines = @($lines | Where-Object { $_ -notmatch '^\s*SUPERSET_PORT\s*=' }) + "SUPERSET_PORT=$novo"
            Set-Content -Path $envFile -Value $lines -Encoding ascii
            docker compose up -d superset
        }
        if ($LASTEXITCODE -ne 0) { throw "docker compose do Superset falhou (codigo $LASTEXITCODE)" }
    } finally { Remove-Item Env:SUPERSET_PORT -ErrorAction SilentlyContinue; Pop-Location }
    $supersetPort = $novo
    Write-Host "Aguardando o Superset reiniciar (importa o dashboard se precisar)..."
    foreach ($i in 1..60) { try { if ((Invoke-WebRequest "http://localhost:$supersetPort/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { break } } catch { Start-Sleep -Seconds 3 } }
}

$chatPort = Get-HostPort $chatName "8099/tcp"
if (-not $chatPort) { $chatPort = 8099; Write-Host "AVISO: o chat nao esta no ar (rode chatbot\up.ps1). O botao 'Pergunte aos dados' so aparece quando ele estiver." -ForegroundColor Yellow }

$env:SUPERSET_PORT = "$supersetPort"; $env:CHAT_PORT = "$chatPort"; $env:GATEWAY_PORT = "$gatewayPort"
Push-Location $here
try { docker compose up -d --force-recreate; if ($LASTEXITCODE -ne 0) { throw "docker compose do gateway falhou (codigo $LASTEXITCODE)" } } finally { Pop-Location }

$ok = $false
foreach ($i in 1..30) {
    try { if ((Invoke-WebRequest "http://localhost:$gatewayPort/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $ok = $true; break } } catch { Start-Sleep -Seconds 2 }
}
if (-not $ok) { Write-Host "AVISO: o gateway subiu, mas o Superset ainda nao respondeu. Aguarde um pouco e abra o link." -ForegroundColor Yellow }

function Read-Var([string]$File, [string]$Key) {
    if (-not (Test-Path $File)) { return "" }
    $m = Select-String -Path $File -Pattern "^\s*$Key\s*=\s*(.*)$" | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value.Trim() } else { return "" }
}
$pass = Read-Var (Join-Path $here "..\superset\.env") "SUPERSET_ADMIN_PASSWORD"
Write-Host ""
Write-Host "=== SISTEMA: http://localhost:$gatewayPort ===" -ForegroundColor Green
Write-Host "Dashboard e chat com IA no mesmo endereco (botao 'Pergunte aos dados')."
Write-Host "Superset: usuario admin / senha $pass   (a leitura do dashboard dispensa login)"
Write-Host "Chave da DeepSeek: entre como admin e abra Settings > Configuracoes do chat (IA). Nada de .env."
