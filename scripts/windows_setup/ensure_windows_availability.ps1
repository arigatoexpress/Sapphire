# Keep the Windows Sapphire desktop reachable for read-only production support.
#
# This script disables sleep/lock paths, preserves rollback evidence, and
# registers user-logon Scheduled Tasks for itself and TradingView CDP. It does
# not enable trade execution, Telegram sends, or browser mutation.

param(
    [string]$RepoPath = "E:\Sapphire\Code\Sapphire",
    [string]$StatusRoot = "$env:USERPROFILE\SapphireOps",
    [string]$TradingViewTaskName = "SapphireTradingViewCDP",
    [string]$AvailabilityTaskName = "SapphireWindowsAvailabilityGuard",
    [switch]$RegisterTasks = $true,
    [switch]$StartTradingViewCdp
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$backupRoot = Join-Path $StatusRoot "backups"
$timestamp = Get-Date -Format "yyyyMMddTHHmmss"
$backupDir = Join-Path $backupRoot "windows-online-hardening-$timestamp"
$statusPath = Join-Path $StatusRoot "windows-availability-status.json"
$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$cdpLauncher = Join-Path $RepoPath "scripts\windows_setup\start_tradingview_cdp.ps1"

New-Item -ItemType Directory -Force -Path $StatusRoot, $backupRoot, $backupDir | Out-Null

$results = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    host = $env:COMPUTERNAME
    user = $currentIdentity
    repo_path = $RepoPath
    backup_dir = $backupDir
    actions = @()
    errors = @()
}

function Add-Action {
    param([string]$Name, [string]$Status, [string]$Detail)
    $script:results.actions += [pscustomobject]@{
        name = $Name
        status = $Status
        detail = $Detail
    }
}

function Add-Error {
    param([string]$Name, [string]$Detail)
    $script:results.errors += [pscustomobject]@{
        name = $Name
        detail = $Detail
    }
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Script)
    try {
        $output = & $Script 2>&1 | Out-String
        Add-Action -Name $Name -Status "ok" -Detail $output.Trim()
    } catch {
        Add-Action -Name $Name -Status "error" -Detail $_.Exception.Message
        Add-Error -Name $Name -Detail $_.Exception.Message
    }
}

Invoke-Step "backup_current_power_state" {
    powercfg /getactivescheme | Set-Content -Path (Join-Path $backupDir "power-scheme-before.txt") -Encoding UTF8
    powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Set-Content -Path (Join-Path $backupDir "sleep-before.txt") -Encoding UTF8
    powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Set-Content -Path (Join-Path $backupDir "display-before.txt") -Encoding UTF8
    reg export "HKCU\Control Panel\Desktop" (Join-Path $backupDir "hkcu-desktop-before.reg") /y | Out-Null
    reg export "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" (Join-Path $backupDir "hklm-system-policy-before.reg") /y | Out-Null
    "backed up power and registry state"
}

Invoke-Step "set_power_never_sleep" {
    powercfg /change standby-timeout-ac 0 | Out-Null
    powercfg /change standby-timeout-dc 0 | Out-Null
    powercfg /change monitor-timeout-ac 0 | Out-Null
    powercfg /change monitor-timeout-dc 0 | Out-Null
    powercfg /hibernate off | Out-Null
    "sleep, monitor timeout, and hibernate are disabled"
}

Invoke-Step "disable_screensaver_lock" {
    reg add "HKCU\Control Panel\Desktop" /v ScreenSaveActive /t REG_SZ /d 0 /f | Out-Null
    reg add "HKCU\Control Panel\Desktop" /v ScreenSaverIsSecure /t REG_SZ /d 0 /f | Out-Null
    reg add "HKCU\Control Panel\Desktop" /v ScreenSaveTimeOut /t REG_SZ /d 0 /f | Out-Null
    reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v InactivityTimeoutSecs /t REG_DWORD /d 0 /f | Out-Null
    "screensaver lock and machine inactivity timeout are disabled"
}

Invoke-Step "ensure_network_remote_services" {
    foreach ($serviceName in @("Tailscale", "sshd")) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            Set-Service -Name $serviceName -StartupType Automatic
            if ($service.Status -ne "Running") {
                Start-Service -Name $serviceName
            }
        }
    }
    "Tailscale and OpenSSH service startup checked"
}

Invoke-Step "backup_scattered_tradingview_startup_files" {
    $paths = @(
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\TradingView-CDP.bat"),
        (Join-Path $env:USERPROFILE "Desktop\TradingView-CDP.bat")
    )

    foreach ($path in $paths) {
        if (Test-Path $path) {
            $name = Split-Path -Leaf $path
            $dest = Join-Path $backupDir $name
            if (Test-Path $dest) {
                $dest = Join-Path $backupDir (($name -replace "\.bat$", "") + "-" + [guid]::NewGuid().ToString("N") + ".bat")
            }
            Move-Item -LiteralPath $path -Destination $dest -Force
        }
    }
    "old TradingView-CDP batch files moved into backup"
}

Invoke-Step "stop_stale_tradingview_cdp_cmd" {
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match "TradingView-CDP\.bat" } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    "stale Startup cmd processes stopped"
}

if ($RegisterTasks) {
    Invoke-Step "register_tradingview_cdp_task" {
        if (-not (Test-Path $cdpLauncher)) {
            throw "Launcher missing at $cdpLauncher"
        }

        $action = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$cdpLauncher`""
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity
        $principal = New-ScheduledTaskPrincipal -UserId $currentIdentity -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
            -RestartCount 3 `
            -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask `
            -TaskName $TradingViewTaskName `
            -Action $action `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description "Start TradingView with read-only CDP on localhost:9222 for Sapphire TV agent." `
            -Force `
            -ErrorAction Stop | Out-Null
        "$TradingViewTaskName logon task registered"
    }

    Invoke-Step "register_availability_guard_task" {
        $self = $PSCommandPath
        $action = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$self`" -RepoPath `"$RepoPath`" -StatusRoot `"$StatusRoot`" -RegisterTasks:`$false"
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity
        $principal = New-ScheduledTaskPrincipal -UserId $currentIdentity -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
        Register-ScheduledTask `
            -TaskName $AvailabilityTaskName `
            -Action $action `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description "Re-apply Sapphire Windows availability settings at user logon." `
            -Force `
            -ErrorAction Stop | Out-Null
        "$AvailabilityTaskName logon task registered"
    }
}

if ($StartTradingViewCdp) {
    Invoke-Step "start_tradingview_cdp_task" {
        Start-ScheduledTask -TaskName $TradingViewTaskName
        "$TradingViewTaskName started"
    }
}

Invoke-Step "readback_after" {
    $after = [ordered]@{
        active_scheme = (powercfg /getactivescheme | Out-String).Trim()
        sleep = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Out-String).Trim()
        display = (powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Out-String).Trim()
        screen_save_active = (reg query "HKCU\Control Panel\Desktop" /v ScreenSaveActive | Out-String).Trim()
        screen_saver_secure = (reg query "HKCU\Control Panel\Desktop" /v ScreenSaverIsSecure | Out-String).Trim()
        screen_save_timeout = (reg query "HKCU\Control Panel\Desktop" /v ScreenSaveTimeOut | Out-String).Trim()
        inactivity_timeout = (reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v InactivityTimeoutSecs | Out-String).Trim()
    }
    $script:results.readback = $after
    "readback captured"
}

$results | ConvertTo-Json -Depth 8 | Set-Content -Path $statusPath -Encoding UTF8
$results | ConvertTo-Json -Depth 8

if ($results.errors.Count -gt 0) {
    exit 1
}
