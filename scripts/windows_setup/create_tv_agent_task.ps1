# Register Sapphire's read-only Windows TradingView workbench agent tasks.
#
# The tasks launch scripts/windows_setup/start_tv_agent.ps1 from the Sapphire
# checkout. The launcher exits 0 if port 8081 is already listening, so startup
# and logon triggers can coexist without fighting over the port.

param(
    [string]$RepoPath = "E:\Sapphire\Code\Sapphire",
    [string]$PythonPath = "python",
    [string]$TaskName = "Sapphire-TV-Agent",
    [string]$LogonTaskName = "Sapphire-TV-Agent-Logon",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8081,
    [string]$CdpUrl = "http://127.0.0.1:9222",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

$launcher = Join-Path $RepoPath "scripts\windows_setup\start_tv_agent.ps1"
if (-not (Test-Path $launcher)) {
    throw "TV agent launcher not found: $launcher"
}
if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    throw "RepoPath is not a git checkout: $RepoPath"
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$launcher`"",
    "-RepoPath", "`"$RepoPath`"",
    "-PythonPath", "`"$PythonPath`"",
    "-HostAddress", $HostAddress,
    "-Port", [string]$Port,
    "-CdpUrl", "`"$CdpUrl`""
) -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$startupPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$startupTrigger.Delay = "PT30S"

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Sapphire read-only Windows TradingView workbench agent on port $Port." `
    -Action $action `
    -Trigger $startupTrigger `
    -Settings $settings `
    -Principal $startupPrincipal `
    -Force | Out-Null

$logonPrincipal = New-ScheduledTaskPrincipal `
    -UserId "$env:COMPUTERNAME\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask `
    -TaskName $LogonTaskName `
    -Description "Sapphire read-only Windows TradingView workbench agent at user logon." `
    -Action $action `
    -Trigger $logonTrigger `
    -Settings $settings `
    -Principal $logonPrincipal `
    -Force | Out-Null

Write-Host "Registered $TaskName and $LogonTaskName for read-only TV agent port $Port."
Write-Host "Launcher: $launcher"
Write-Host "Start manually: Start-ScheduledTask -TaskName $TaskName"

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started $TaskName."
}

