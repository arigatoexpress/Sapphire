# Install the Sapphire Windows Research Worker scheduled task.
#
# Run manually from an elevated PowerShell on DESKTOP-HFCK6U9. This installer
# registers the task but does not start it. The task runs paper-only research
# workloads through run_research_worker.ps1.

param(
    [string]$TaskName = "SapphireResearchWorker",
    [string]$RepoPath = "E:\Sapphire\Code\Sapphire",
    [string]$WorkerScript = "",
    [string]$OutputRoot = "E:\Sapphire\research-worker",
    [string]$RunTime = "02:30",
    [int]$BacktestDays = 90,
    [decimal]$Bankroll = 10000
)

$ErrorActionPreference = "Stop"

if (-not $WorkerScript) {
    $WorkerScript = Join-Path $RepoPath "scripts\windows_setup\run_research_worker.ps1"
}

if (-not (Test-Path $WorkerScript)) {
    throw "Worker script not found: $WorkerScript"
}

if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    throw "RepoPath is not a git checkout: $RepoPath"
}

$time = [DateTime]::ParseExact($RunTime, "HH:mm", $null)
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$WorkerScript`"",
    "-RepoPath", "`"$RepoPath`"",
    "-OutputRoot", "`"$OutputRoot`"",
    "-BacktestDays", [string]$BacktestDays,
    "-Bankroll", [string]$Bankroll
) -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:COMPUTERNAME\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Sapphire paper-only Windows research worker: backtests and walk-forward artifacts." `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Registered $TaskName for $RunTime. It has not been started."
Write-Host "Inspect with: Get-ScheduledTask -TaskName $TaskName"
Write-Host "Start manually only when ready: Start-ScheduledTask -TaskName $TaskName"
