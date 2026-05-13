# Sapphire OS — Windows Server Setup Script
# Run this on the Windows PC to configure it as a 24/7 always-on server.
# Run as Administrator: powershell -ExecutionPolicy Bypass -File setup_windows_server.ps1

Write-Host "=== Sapphire Windows Server Setup ===" -ForegroundColor Cyan

# 1. Disable sleep/hibernate
Write-Host "`n[1/5] Disabling sleep and hibernate..." -ForegroundColor Yellow
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
powercfg /change monitor-timeout-ac 30  # Turn off monitor after 30 min (saves power, PC stays on)
powercfg /hibernate off
Write-Host "  Sleep/hibernate disabled" -ForegroundColor Green

# 2. Set high performance power plan
Write-Host "`n[2/5] Setting high performance power plan..." -ForegroundColor Yellow
$highPerf = powercfg /list | Select-String "High performance"
if ($highPerf) {
    $guid = ($highPerf -split '\s+')[3]
    powercfg /setactive $guid
    Write-Host "  High performance plan activated" -ForegroundColor Green
} else {
    Write-Host "  High performance plan not found, using current" -ForegroundColor Yellow
}

# 3. Ensure Ollama starts on boot
Write-Host "`n[3/5] Configuring Ollama auto-start..." -ForegroundColor Yellow
$ollamaPath = "C:\Users\aribs\AppData\Local\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaPath) {
    # Set OLLAMA_HOST to listen on all interfaces (for Tailscale access)
    [System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0", "User")

    # Create startup shortcut
    $startupFolder = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup")
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut("$startupFolder\Ollama.lnk")
    $shortcut.TargetPath = $ollamaPath
    $shortcut.Arguments = "serve"
    $shortcut.Save()
    Write-Host "  Ollama configured for auto-start with OLLAMA_HOST=0.0.0.0" -ForegroundColor Green
} else {
    Write-Host "  Ollama not found at expected path" -ForegroundColor Red
}

# 4. Ensure SapphireWebhook scheduled task is set to run at startup
Write-Host "`n[4/5] Verifying webhook scheduled task..." -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName "SapphireWebhook" -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "  SapphireWebhook task exists (Status: $($task.State))" -ForegroundColor Green
} else {
    Write-Host "  SapphireWebhook task not found — create it manually" -ForegroundColor Yellow
}

# 5. Pull latest repos
Write-Host "`n[5/5] Pulling latest repos..." -ForegroundColor Yellow
# Note: Cointracker and claw-code were archived 2026-05-12 and no longer exist at ~/Code/.
$repos = @("Sapphire", "Project-Go-Forward", "cyber-threat-bot", "regional-intel-workbench")
foreach ($repo in $repos) {
    $path = "E:\Sapphire\Code\$repo"
    if (Test-Path "$path\.git") {
        Push-Location $path
        git pull 2>&1 | Out-Null
        $commit = git log --oneline -1
        Write-Host "  $repo`: $commit" -ForegroundColor Gray
        Pop-Location
    }
}

Write-Host "`n=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "Windows PC is configured as a 24/7 Sapphire server."
Write-Host "Ollama will auto-start on boot and listen on all interfaces."
Write-Host "Power management: sleep disabled, monitor off after 30 min."
