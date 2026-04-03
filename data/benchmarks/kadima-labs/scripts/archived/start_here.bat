@echo off
echo ==================================================
echo  Qwen 3.5 Testing Suite - Quick Start
echo ==================================================
echo.

cd /d C:\Users\aribs\AI_Benchmark

:: Check Ollama version first
echo Step 1: Checking Ollama version...
python check_ollama_update.py
if errorlevel 1 (
    echo.
    echo ==================================================
    echo  UPDATE REQUIRED
echo ==================================================
    echo.
    echo Please update Ollama before continuing.
    echo.
    echo Option 1: Right-click Ollama in system tray ^> Restart to update
echo Option 2: Download from https://ollama.com/download
echo Option 3: Run: update_ollama_and_test.ps1
echo.
    pause
    exit /b 1
)

echo.
echo Step 2: Checking for Qwen 3.5 models...
python -c "import subprocess; r=subprocess.run(['ollama','list'], capture_output=True, text=True); print('Installed models:'); [print('  -', line.split()[0]) for line in r.stdout.split('\n')[1:] if 'qwen' in line.lower() and line.strip()]; exit(0 if any('qwen3.5' in line for line in r.stdout.split('\n')) else 1)"
if errorlevel 1 (
    echo.
    echo Qwen 3.5 models not found. Pulling them now...
    echo This will download ~26GB and may take 30-60 minutes.
    echo.
    set /p confirm="Continue? (y/n): "
    if /i not "%confirm%"=="y" exit /b 0
    
    echo.
    echo Downloading qwen3.5:9b...
    ollama pull qwen3.5:9b
    
    echo.
    echo Downloading qwen3.5:27b...
    ollama pull qwen3.5:27b
)

echo.
echo Step 3: Running comprehensive tests...
echo This will take 30-60 minutes depending on models installed.
echo.

python comprehensive_qwen35_test.py

echo.
echo ==================================================
echo  Testing Complete!
echo ==================================================
echo.
echo Results saved. Check the following files:
dir /b comprehensive_test_*.json 2^>nul
dir /b viz_*.png 2^>nul
echo.
pause
