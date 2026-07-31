[CmdletBinding()]
param(
    [switch]$Start
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$taskName = "Sapphire-MegaETH-Observer-Anchor"
$distribution = "Ubuntu-24.04"
$serviceName = "sapphire-megaeth-ingest.service"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    throw "$taskName already exists; refusing to replace it"
}

$wsl = (Get-Command wsl.exe -ErrorAction Stop).Source
$linuxCommand = (
    "sudo --non-interactive systemctl start sapphire-megaeth-ingest.service" +
    " && while sudo --non-interactive systemctl is-active --quiet " +
    "sapphire-megaeth-ingest.service; do /bin/sleep 30; done"
)
$arguments = "-d $distribution --exec /bin/bash -lc `"$linuxCommand`""

$action = New-ScheduledTaskAction -Execute $wsl -Argument $arguments
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $identity `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Settings $settings `
    -Principal $principal | Out-Null

if ($Start) {
    Start-ScheduledTask -TaskName $taskName
}

[ordered]@{
    schema = "sapphire/megaeth-wsl-observer-anchor-registration/v1"
    task_name = $taskName
    distribution = $distribution
    service = $serviceName
    trigger_count = 0
    automatic_restart = $false
    started = [bool]$Start
} | ConvertTo-Json -Compress
