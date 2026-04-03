@echo off
chcp 65001 >nul
echo ==================================================
echo  Qwen 3.5 Comprehensive Testing Suite
echo ==================================================
echo.

:: Check if Ollama is running
tasklist | findstr "ollama.exe" >nul
if errorlevel 1 (
    echo ERROR: Ollama is not running!
    echo Please start Ollama first.
    pause
    exit /b 1
)

:: Check Python
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.10 or later.
    pause
    exit /b 1
)

echo OK - Python found
echo.

:: Check required packages
echo Checking required packages...
python -c "import matplotlib, numpy, pynvml" 2>nul
if errorlevel 1 (
    echo Installing required packages...
    pip install matplotlib numpy pynvml
)

echo OK - Dependencies ready
echo.

:: Run the comprehensive test
cd /d C:\Users\aribs\AI_Benchmark
echo Starting comprehensive tests...
echo This may take 30-60 minutes depending on models installed.
echo.

python comprehensive_qwen35_test.py

echo.
echo ==================================================
echo  Testing Complete!
echo ==================================================
echo.
echo Generated visualizations:
dir /b viz_*.png 2>nul
echo.
pause
