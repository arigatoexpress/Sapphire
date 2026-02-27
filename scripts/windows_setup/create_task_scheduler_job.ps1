# Windows Task Scheduler Setup for TradingView Agent
# Run this on Windows PC as Administrator to auto-start TV Agent on boot

$taskName = "TradingViewAutonomousManager"
$taskDescription = "TradingView Desktop Autonomous Manager - Sapphire Integration"

# Find the installation path
$possiblePaths = @(
    "C:\TradingViewAutonomousManager",
    "C:\sapphire\tv-agent",
    "D:\TradingViewAutonomousManager",
    "$env:USERPROFILE\TradingViewAutonomousManager"
)

$installPath = $null
foreach ($path in $possiblePaths) {
    if (Test-Path $path) {
        $installPath = $path
        break
    }
}

if (-not $installPath) {
    Write-Host "❌ ERROR: TradingViewAutonomousManager not found!" -ForegroundColor Red
    Write-Host "Checked locations:" -ForegroundColor Yellow
    $possiblePaths | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

Write-Host "✅ Found installation at: $installPath" -ForegroundColor Green

# Create startup script
$startupScript = @"
@echo off
cd /d "$installPath\backend"
call .\venv\Scripts\activate.bat
uvicorn main:app --host 0.0.0.0 --port 8081 --log-level info
"@

$scriptPath = "$installPath\start_agent.bat"
$startupScript | Out-File -FilePath $scriptPath -Encoding ASCII

Write-Host "✅ Created startup script: $scriptPath" -ForegroundColor Green

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "⚠️  Task '$taskName' already exists. Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create the scheduled task
$action = New-ScheduledTaskAction -Execute $scriptPath

# Trigger: At startup, with 30 second delay for network
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = "PT30S"  # 30 seconds

# Settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

# Run as current user with highest privileges
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:COMPUTERNAME\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Description $taskDescription `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force

    Write-Host "✅ Task '$taskName' created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor Cyan
    Write-Host "  - Name: $taskName"
    Write-Host "  - Trigger: At system startup (30s delay)"
    Write-Host "  - Run as: $env:USERNAME"
    Write-Host ""
    Write-Host "Commands to manage:" -ForegroundColor Cyan
    Write-Host "  Start:  Start-ScheduledTask -TaskName '$taskName'"
    Write-Host "  Stop:   Stop-Process -Name python (or stop uvicorn)"
    Write-Host "  View:   Get-ScheduledTask -TaskName '$taskName'"
    Write-Host ""
    
    # Start the task now
    $startNow = Read-Host "Start the agent now? (y/n)"
    if ($startNow -eq 'y' -or $startNow -eq 'Y') {
        Start-ScheduledTask -TaskName $taskName
        Start-Sleep -Seconds 3
        Write-Host "🚀 Agent started! Check http://100.71.10.48:8081" -ForegroundColor Green
    }

} catch {
    Write-Host "❌ Failed to create task: $_" -ForegroundColor Red
}
