# TradingView Agent - Windows Recovery Script
# Run this on your Windows PC as Administrator

Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  TradingView Desktop Autonomous Manager - Recovery Check" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Check common locations
$locations = @(
    "C:\TradingViewAutonomousManager",
    "C:\sapphire\tv-agent",
    "C:\tv-agent",
    "D:\TradingViewAutonomousManager",
    "$env:USERPROFILE\TradingViewAutonomousManager"
)

$found = $null
foreach ($loc in $locations) {
    if (Test-Path $loc) {
        Write-Host "✅ Found: $loc" -ForegroundColor Green
        $found = $loc
        break
    } else {
        Write-Host "❌ Not found: $loc" -ForegroundColor DarkGray
    }
}

Write-Host ""

if ($found) {
    Write-Host "Found TV Agent at: $found" -ForegroundColor Green
    Write-Host ""

    # Check if Python/venv exists
    $venvPath = Join-Path $found "backend\venv\Scripts\activate.bat"
    $mainPath = Join-Path $found "backend\main.py"

    if (Test-Path $venvPath) {
        Write-Host "✅ Virtual environment found" -ForegroundColor Green

        $choice = Read-Host "Start the TV Agent now? (y/n)"

        if ($choice -eq 'y' -or $choice -eq 'Y') {
            Write-Host ""
            Write-Host "Starting TV Agent..." -ForegroundColor Yellow

            $backendPath = Join-Path $found "backend"
            Set-Location $backendPath

            # Activate and start
            cmd /c "venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 8081"
        }
    } else {
        Write-Host "⚠️  Virtual environment not found. Need to setup." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Run these commands to setup:" -ForegroundColor Cyan
        Write-Host "  cd $found\backend"
        Write-Host "  python -m venv venv"
        Write-Host "  .\venv\Scripts\activate"
        Write-Host "  pip install -r requirements.txt"
        Write-Host "  playwright install chromium"
    }
} else {
    Write-Host "❌ TV Agent not found on this system!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  1. Restore from backup"
    Write-Host "  2. Re-download from GitHub"
    Write-Host "  3. Copy from Mac via: scp -r user@mac:~/TradingViewAutonomousManager C:\"
    Write-Host ""
    Write-Host "Or create fresh install directory and let me know - I have the code ready!"
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
