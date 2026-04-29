# Sapphire Windows Research Worker
#
# Runs paper-only research workloads on the Windows desktop and writes artifacts
# outside canonical live-trading paths. This script does not submit orders, sign
# payloads, send Telegram messages, or mutate scheduled tasks.

param(
    [string]$RepoPath = "E:\Sapphire\Code\Sapphire",
    [string]$OutputRoot = "E:\Sapphire\research-worker",
    [int]$BacktestDays = 90,
    [decimal]$Bankroll = 10000,
    [string]$WalkforwardStrategies = "RegimeAwareRSI",
    [string]$WalkforwardSymbol = "BTC-USD",
    [string]$WalkforwardHorizons = "90",
    [ValidateSet("synthetic", "yfinance")]
    [string]$WalkforwardBarsSource = "synthetic",
    [switch]$SkipBacktest,
    [switch]$SkipWalkforward
)

$ErrorActionPreference = "Stop"

function New-SafeDirectory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Invoke-WorkerCommand {
    param(
        [string]$Name,
        [string[]]$Command,
        [string]$LogPath
    )

    $started = [DateTime]::UtcNow
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $Command[0] $Command[1..($Command.Length - 1)] 2>&1 | ForEach-Object {
            $_.ToString()
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
    $output | Out-File -FilePath $LogPath -Encoding utf8
    $finished = [DateTime]::UtcNow

    return [ordered]@{
        name = $Name
        command = ($Command -join " ")
        started_at = $started.ToString("o")
        finished_at = $finished.ToString("o")
        exit_code = $exitCode
        log_path = $LogPath
    }
}

if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    throw "RepoPath is not a git checkout: $RepoPath"
}

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $OutputRoot $stamp
$backtestDir = Join-Path $runDir "backtest"
$walkforwardDir = Join-Path $runDir "walkforward"
New-SafeDirectory -Path $backtestDir
New-SafeDirectory -Path $walkforwardDir

Push-Location $RepoPath
try {
    $gitSha = (git rev-parse HEAD).Trim()
    $manifest = [ordered]@{
        schema_version = 1
        generated_at = [DateTime]::UtcNow.ToString("o")
        host = $env:COMPUTERNAME
        repo_path = $RepoPath
        git_sha = $gitSha
        paper_only = $true
        live_trading_enabled = $false
        telegram_sends_enabled = $false
        output_root = $OutputRoot
        run_dir = $runDir
        commands = @()
        artifacts = @()
    }

    if (-not $SkipBacktest) {
        $logPath = Join-Path $runDir "backtest.log"
        $cmd = @(
            "python",
            "-m", "lib.analytics.run_strategies",
            "--days", [string]$BacktestDays,
            "--bankroll", [string]$Bankroll,
            "--output-dir", $backtestDir
        )
        $manifest.commands += Invoke-WorkerCommand -Name "strategy_sweep" -Command $cmd -LogPath $logPath
        $manifest.artifacts += $backtestDir
    }

    if (-not $SkipWalkforward) {
        $logPath = Join-Path $runDir "walkforward.log"
        $cmd = @(
            "python",
            "-m", "services.walkforward.build",
            "--strategies", $WalkforwardStrategies,
            "--symbol", $WalkforwardSymbol,
            "--horizons", $WalkforwardHorizons,
            "--train", "60",
            "--test", "20",
            "--advance", "20",
            "--bars-source", $WalkforwardBarsSource,
            "--output", $walkforwardDir
        )
        $manifest.commands += Invoke-WorkerCommand -Name "walkforward" -Command $cmd -LogPath $logPath
        $manifest.artifacts += $walkforwardDir
    }

    $manifestPath = Join-Path $runDir "manifest.json"
    $manifest | ConvertTo-Json -Depth 8 | Out-File -FilePath $manifestPath -Encoding utf8
    Write-Host "Sapphire research worker complete: $manifestPath"

    $failed = @($manifest.commands | Where-Object { $_.exit_code -ne 0 })
    if ($failed.Count -gt 0) {
        exit 1
    }
}
finally {
    Pop-Location
}
