# Start TradingView Desktop with local Chrome DevTools Protocol enabled.
#
# This is a read-only observability launcher for the Windows TV agent. It does
# not enable trade execution, Telegram sends, or browser mutation.

param(
    [int]$CdpPort = 9222,
    [string]$StatusRoot = "$env:USERPROFILE\SapphireOps"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$logRoot = Join-Path $StatusRoot "logs"
$flagsRoot = Join-Path $env:APPDATA "TradingView"
$statusPath = Join-Path $StatusRoot "tradingview-cdp-status.json"
$logPath = Join-Path $logRoot "tradingview-cdp.log"
$cdpUrl = "http://127.0.0.1:$CdpPort"

New-Item -ItemType Directory -Force -Path $StatusRoot, $logRoot, $flagsRoot | Out-Null

function Write-Status {
    param(
        [string]$Status,
        [string]$Message,
        [object]$Package,
        [string]$Executable,
        [object]$Probe
    )

    $payload = [pscustomobject]@{
        timestamp = (Get-Date).ToString("o")
        status = $Status
        message = $Message
        package = if ($Package) { $Package.PackageFullName } else { $null }
        executable = $Executable
        cdp_url = $cdpUrl
        tradingview_pids = @(Get-Process TradingView -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
        probe = $Probe
        safety = [pscustomobject]@{
            trading_execution_enabled = $false
            telegram_sends_enabled = $false
            browser_mutation_enabled = $false
        }
    }

    $payload | ConvertTo-Json -Depth 6 | Set-Content -Path $statusPath -Encoding UTF8
    "$($payload.timestamp) $Status $Message" | Add-Content -Path $logPath -Encoding UTF8
}

$package = $null
$exe = $null
$probe = $null

try {
    Set-Content `
        -Path (Join-Path $flagsRoot "electron-flags.cfg") `
        -Value "--remote-debugging-port=$CdpPort" `
        -NoNewline `
        -Encoding ASCII

    $package = Get-AppxPackage -Name "TradingView.Desktop" |
        Sort-Object -Property Version -Descending |
        Select-Object -First 1

    if (-not $package) {
        throw "TradingView.Desktop package is not installed."
    }

    $exe = Join-Path $package.InstallLocation "TradingView.exe"
    if (-not (Test-Path $exe)) {
        throw "TradingView executable not found at $exe"
    }

    Get-Process TradingView -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue

    Start-Sleep -Seconds 2
    Start-Process `
        -FilePath $exe `
        -ArgumentList "--remote-debugging-port=$CdpPort" `
        -WorkingDirectory $package.InstallLocation

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "$cdpUrl/json/version" -TimeoutSec 2
            $probe = [pscustomobject]@{
                ok = $true
                status_code = [int]$response.StatusCode
                body_sample = $response.Content.Substring(0, [Math]::Min(500, $response.Content.Length))
            }
            Write-Status -Status "ok" -Message "TradingView CDP is reachable." -Package $package -Executable $exe -Probe $probe
            exit 0
        } catch {
            $probe = [pscustomobject]@{
                ok = $false
                error = $_.Exception.Message
            }
        }
    }

    Write-Status -Status "cdp_unreachable_after_launch" -Message "TradingView launched but CDP did not answer within 20 seconds." -Package $package -Executable $exe -Probe $probe
    exit 2
} catch {
    Write-Status -Status "error" -Message $_.Exception.Message -Package $package -Executable $exe -Probe $probe
    exit 1
}
