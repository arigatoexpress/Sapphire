@echo off
echo ===============================================================
echo  SAPPHIRE TV AGENT - QUICK START
echo ===============================================================
echo.

REM Configuration
set "TV_AGENT_PORT=8081"
set "TV_AGENT_DIR=C:\TradingViewAutonomousManager\backend"

echo [1/3] Checking if TV Agent is already running...
netstat -ano | findstr ":%TV_AGENT_PORT%" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    echo.
    echo [OK] TV Agent is already running on port %TV_AGENT_PORT%!
    echo.
    echo Testing endpoint...
    curl -s http://localhost:%TV_AGENT_PORT%/health
    echo.
    echo.
    echo [URL] http://100.71.10.48:%TV_AGENT_PORT%
    echo.
    goto end
)

echo [OK] TV Agent not running - will start now
echo.

REM Find installation
echo [2/3] Locating TV Agent installation...
set "FOUND_DIR="

if exist "C:\TradingViewAutonomousManager\backend\main.py" (
    set "FOUND_DIR=C:\TradingViewAutonomousManager\backend"
) else if exist "C:\sapphire\tv-agent\backend\main.py" (
    set "FOUND_DIR=C:\sapphire\tv-agent\backend"
) else if exist "%USERPROFILE%\TradingViewAutonomousManager\backend\main.py" (
    set "FOUND_DIR=%USERPROFILE%\TradingViewAutonomousManager\backend"
)

if not defined FOUND_DIR (
    echo [ERROR] TV Agent not found in common locations!
    echo.
    echo Checked:
    echo   - C:\TradingViewAutonomousManager\backend
    echo   - C:\sapphire\tv-agent\backend
    echo   - %USERPROFILE%\TradingViewAutonomousManager\backend
    echo.
    echo Please specify the correct path:
    set /p "FOUND_DIR=Enter path to backend folder: "
)

echo [OK] Found: %FOUND_DIR%
echo.

REM Check venv
echo [3/3] Checking virtual environment...
if not exist "%FOUND_DIR%\venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Run setup first:
    echo   cd %FOUND_DIR%
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo   playwright install chromium
    goto end
)

echo [OK] Virtual environment found
echo.

REM Start the service
echo ===============================================================
echo  STARTING TV AGENT
echo ===============================================================
echo.
echo This window will stay open while TV Agent runs.
echo Press Ctrl+C to stop, or close this window.
echo.
echo API will be available at:
echo   http://100.71.10.48:%TV_AGENT_PORT%
echo   http://100.71.10.48:%TV_AGENT_PORT%/health
echo   http://100.71.10.48:%TV_AGENT_PORT%/docs
echo.
echo ===============================================================
echo.

cd /d "%FOUND_DIR%"
call venv\Scripts\activate.bat

uvicorn main:app --host 0.0.0.0 --port %TV_AGENT_PORT% --log-level info

:end
echo.
echo [TV Agent stopped or already running]
echo.
pause
