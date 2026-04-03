# PowerShell script to update Ollama and test Qwen 3.5
# Run as Administrator

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Ollama Update & Qwen 3.5 Testing Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check current version
Write-Host "Step 1: Checking current Ollama version..." -ForegroundColor Yellow
try {
    $currentVersion = ollama --version 2>&1
    Write-Host "Current: $currentVersion" -ForegroundColor White
} catch {
    Write-Host "Ollama not found or not in PATH" -ForegroundColor Red
    exit 1
}

# Check if we need to update
if ($currentVersion -match "0\.17\.[0-4]") {
    Write-Host "`n⚠️  Update required! Need v0.17.5+ for Qwen 3.5" -ForegroundColor Red
    
    # Download latest Ollama
    Write-Host "`nStep 2: Downloading latest Ollama..." -ForegroundColor Yellow
    $downloadUrl = "https://ollama.com/download/OllamaSetup.exe"
    $outputPath = "$env:TEMP\OllamaSetup.exe"
    
    try {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $outputPath -UseBasicParsing
        Write-Host "✓ Downloaded to $outputPath" -ForegroundColor Green
    } catch {
        Write-Host "✗ Download failed. Please manually download from https://ollama.com/download" -ForegroundColor Red
        exit 1
    }
    
    # Install
    Write-Host "`nStep 3: Installing Ollama update..." -ForegroundColor Yellow
    Write-Host "Please complete the installation wizard..." -ForegroundColor Cyan
    Start-Process -FilePath $outputPath -Wait
    
    # Verify update
    Write-Host "`nStep 4: Verifying update..." -ForegroundColor Yellow
    $newVersion = ollama --version 2>&1
    Write-Host "New version: $newVersion" -ForegroundColor White
    
    if ($newVersion -match "0\.17\.[5-9]" -or $newVersion -match "0\.1[8-9]") {
        Write-Host "✓ Update successful!" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Please restart your computer and re-run this script" -ForegroundColor Yellow
        exit 0
    }
} else {
    Write-Host "✓ Ollama is up to date!" -ForegroundColor Green
}

# Pull Qwen 3.5 models
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Step 5: Downloading Qwen 3.5 Models" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$models = @("qwen3.5:9b", "qwen3.5:27b")

foreach ($model in $models) {
    Write-Host "Pulling $model..." -ForegroundColor Yellow
    ollama pull $model
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ $model installed successfully" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to install $model" -ForegroundColor Red
    }
    Write-Host ""
}

# List installed models
Write-Host "Step 6: Verifying installations..." -ForegroundColor Yellow
ollama list | Select-String "qwen"

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "To run comprehensive tests, execute:" -ForegroundColor Cyan
Write-Host "  cd C:\Users\aribs\AI_Benchmark" -ForegroundColor White
Write-Host "  python comprehensive_qwen35_test.py" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to continue"
