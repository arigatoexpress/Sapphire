@echo off
echo ===============================================================
echo  SAPPHIRE TV AGENT - QUICK START
echo ===============================================================
echo.

REM Configuration
set "TV_AGENT_PORT=8081"
set "TV_AGENT_REPO=E:\Sapphire\Code\Sapphire"
set "TV_AGENT_LAUNCHER=%TV_AGENT_REPO%\scripts\windows_setup\start_tv_agent.ps1"

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

REM Find repo-owned launcher
echo [2/3] Locating repo-owned TV Agent launcher...
if not exist "%TV_AGENT_LAUNCHER%" (
    echo [ERROR] TV Agent launcher not found!
    echo Expected: %TV_AGENT_LAUNCHER%
    echo.
    echo Update the checkout first:
    echo   cd /d %TV_AGENT_REPO%
    echo   git pull --ff-only
    goto end
)

echo [OK] Found: %TV_AGENT_LAUNCHER%
echo.

REM Check Python
echo [3/3] Checking Python...
python --version >nul 2>nul
if not %errorlevel% == 0 (
    echo [ERROR] Python was not found on PATH.
    echo Pass an explicit Python path to scripts\windows_setup\create_tv_agent_task.ps1.
    goto end
)

echo [OK] Python available
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

powershell -NoProfile -ExecutionPolicy Bypass -File "%TV_AGENT_LAUNCHER%" -RepoPath "%TV_AGENT_REPO%" -HostAddress 0.0.0.0 -Port %TV_AGENT_PORT%

:end
echo.
echo [TV Agent stopped or already running]
echo.
pause
