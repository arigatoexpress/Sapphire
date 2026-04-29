# Start Sapphire's read-only Windows TradingView workbench agent.
#
# This launches a repo-owned service on port 8081. It is intentionally
# read-only: no trade execution, no Telegram sends, and no browser mutations.

param(
    [string]$RepoPath = "E:\Sapphire\Code\Sapphire",
    [string]$PythonPath = "python",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8081,
    [string]$CdpUrl = "http://127.0.0.1:9222"
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:SAPPHIRE_TV_AGENT_READ_ONLY = "1"

$serverPath = Join-Path $RepoPath "services\windows_tv_agent\server.py"
if (-not (Test-Path $serverPath)) {
    throw "Windows TV agent server not found: $serverPath"
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    Write-Host "Sapphire Windows TV agent already listening on port $Port (PID $($listener.OwningProcess))."
    exit 0
}

Push-Location $RepoPath
try {
    & $PythonPath -m services.windows_tv_agent.server `
        --host $HostAddress `
        --port $Port `
        --cdp-url $CdpUrl
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

