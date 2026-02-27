@echo off
echo ===============================================================
echo  TradingView Desktop Autonomous Manager - Quick Start
echo ===============================================================
echo.

REM Check for TV Agent in common locations
set "TV_PATH="

if exist "C:\TradingViewAutonomousManager" (
    set "TV_PATH=C:\TradingViewAutonomousManager"
) else if exist "C:\sapphire\tv-agent" (
    set "TV_PATH=C:\sapphire\tv-agent"
) else if exist "D:\TradingViewAutonomousManager" (
    set "TV_PATH=D:\TradingViewAutonomousManager"
) else if exist "%USERPROFILE%\TradingViewAutonomousManager" (
    set "TV_PATH=%USERPROFILE%\TradingViewAutonomousManager"
)

if "%TV_PATH%"=="" (
    echo [ERROR] TradingView Agent not found!
    echo.
    echo Checked locations:
    echo   - C:\TradingViewAutonomousManager
    echo   - C:\sapphire\tv-agent
    echo   - D:\TradingViewAutonomousManager
    echo   - %USERPROFILE%\TradingViewAutonomousManager
    echo.
    echo Please restore the project files first.
    pause
    exit /b 1
)

echo [OK] Found TV Agent at: %TV_PATH%
echo.

REM Navigate to backend
cd /d "%TV_PATH%\backend"

REM Check for venv
if not exist "venv\Scripts\activate.bat" (
    echo [WARNING] Virtual environment not found!
    echo.
    echo Run setup first:
    echo   cd %TV_PATH%\backend
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo   playwright install chromium
    pause
    exit /b 1
)

echo [OK] Starting TV Agent on port 8081...
echo.
echo Press Ctrl+C to stop
echo.

REM Activate and start
call venv\Scripts\activate.bat
uvicorn main:app --host 0.0.0.0 --port 8081

pause
