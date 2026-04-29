@echo off
setlocal EnableDelayedExpansion

echo ===============================================================
echo  SAPPHIRE WINDOWS SERVICES MANAGER
echo ===============================================================
echo.

REM Configuration
set "WEBHOOK_PORT=9090"
set "TV_AGENT_PORT=8081"
set "WEBHOOK_DIR=C:\sapphire\services\workbench\tradingview"
set "TV_AGENT_REPO=E:\Sapphire\Code\Sapphire"
set "TV_AGENT_LAUNCHER=%TV_AGENT_REPO%\scripts\windows_setup\start_tv_agent.ps1"

REM Check which services are running
echo [1/4] Checking current service status...
echo.

set "WEBHOOK_RUNNING=0"
set "TV_AGENT_RUNNING=0"

netstat -ano | findstr ":%WEBHOOK_PORT%" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    set "WEBHOOK_RUNNING=1"
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%WEBHOOK_PORT%" ^| findstr "LISTENING"') do (
        set "WEBHOOK_PID=%%a"
    )
    echo [OK] Webhook Receiver (port %WEBHOOK_PORT%) - RUNNING (PID: !WEBHOOK_PID!)
) else (
    echo [DOWN] Webhook Receiver (port %WEBHOOK_PORT%) - NOT RUNNING
)

netstat -ano | findstr ":%TV_AGENT_PORT%" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    set "TV_AGENT_RUNNING=1"
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%TV_AGENT_PORT%" ^| findstr "LISTENING"') do (
        set "TV_AGENT_PID=%%a"
    )
    echo [OK] TV Agent (port %TV_AGENT_PORT%) - RUNNING (PID: !TV_AGENT_PID!)
) else (
    echo [DOWN] TV Agent (port %TV_AGENT_PORT%) - NOT RUNNING
)

echo.

REM Menu
echo ===============================================================
echo  COMMANDS
echo ===============================================================
echo.
echo  1. Start Webhook Receiver only (port %WEBHOOK_PORT%)
echo  2. Start TV Agent only (port %TV_AGENT_PORT%)
echo  3. Start BOTH services
if %WEBHOOK_RUNNING% == 1 (
    echo  4. Restart Webhook Receiver
    echo  5. Stop Webhook Receiver
)
if %TV_AGENT_RUNNING% == 1 (
    echo  6. Restart TV Agent
    echo  7. Stop TV Agent
)
echo  8. Check status
echo  9. View logs
echo  0. Exit
echo.

set /p choice="Enter choice (0-9): "

if "%choice%"=="1" goto start_webhook
if "%choice%"=="2" goto start_tv_agent
if "%choice%"=="3" goto start_both
if "%choice%"=="4" goto restart_webhook
if "%choice%"=="5" goto stop_webhook
if "%choice%"=="6" goto restart_tv_agent
if "%choice%"=="7" goto stop_tv_agent
if "%choice%"=="8" goto check_status
if "%choice%"=="9" goto view_logs
if "%choice%"=="0" goto exit

goto exit

:start_webhook
echo.
echo [INFO] Starting Webhook Receiver...
if %WEBHOOK_RUNNING% == 1 (
    echo [WARN] Webhook is already running!
    goto end
)

cd /d "%WEBHOOK_DIR%"
if not exist "webhook_receiver.py" (
    echo [ERROR] webhook_receiver.py not found in %WEBHOOK_DIR%
    goto end
)

start "Sapphire Webhook" python webhook_receiver.py
timeout /t 2 /nobreak >nul

curl -s http://localhost:%WEBHOOK_PORT%/status | findstr "active" >nul
if %errorlevel% == 0 (
    echo [SUCCESS] Webhook Receiver started successfully!
    echo [URL] http://100.71.10.48:%WEBHOOK_PORT%/webhook/tradingview
) else (
    echo [ERROR] Webhook failed to start. Check logs.
)
goto end

:start_tv_agent
echo.
echo [INFO] Starting TV Agent...
if %TV_AGENT_RUNNING% == 1 (
    echo [WARN] TV Agent is already running!
    goto end
)

if not exist "%TV_AGENT_LAUNCHER%" (
    echo [ERROR] TV Agent launcher not found!
    echo [INFO] Expected: %TV_AGENT_LAUNCHER%
    goto end
)

cd /d "%TV_AGENT_REPO%"
start "TradingView Agent" powershell -NoProfile -ExecutionPolicy Bypass -File "%TV_AGENT_LAUNCHER%" -RepoPath "%TV_AGENT_REPO%" -HostAddress 0.0.0.0 -Port %TV_AGENT_PORT%
timeout /t 3 /nobreak >nul

curl -s http://localhost:%TV_AGENT_PORT%/health | findstr "windows_tv_agent" >nul
if %errorlevel% == 0 (
    echo [SUCCESS] TV Agent started successfully!
    echo [URL] http://100.71.10.48:%TV_AGENT_PORT%
) else (
    echo [WARN] TV Agent starting... wait 5s and check status
    timeout /t 5 /nobreak >nul
    curl -s http://localhost:%TV_AGENT_PORT%/health
)
goto end

:start_both
echo.
echo [INFO] Starting BOTH services...
call :start_webhook
timeout /t 2 /nobreak >nul
call :start_tv_agent
goto end

:restart_webhook
echo.
echo [INFO] Restarting Webhook Receiver...
call :stop_webhook
timeout /t 2 /nobreak >nul
call :start_webhook
goto end

:stop_webhook
echo.
echo [INFO] Stopping Webhook Receiver...
if %WEBHOOK_RUNNING% == 0 (
    echo [WARN] Webhook is not running
    goto end
)
taskkill /PID %WEBHOOK_PID% /F
echo [OK] Webhook stopped
goto end

:restart_tv_agent
echo.
echo [INFO] Restarting TV Agent...
call :stop_tv_agent
timeout /t 2 /nobreak >nul
call :start_tv_agent
goto end

:stop_tv_agent
echo.
echo [INFO] Stopping TV Agent...
if %TV_AGENT_RUNNING% == 0 (
    echo [WARN] TV Agent is not running
    goto end
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%TV_AGENT_PORT%" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F 2>nul
)
echo [OK] TV Agent stopped
goto end

:check_status
echo.
echo ===============================================================
echo  DETAILED STATUS CHECK
echo ===============================================================
echo.

REM Webhook
curl -s http://localhost:%WEBHOOK_PORT%/status > webhook_status.json 2>nul
if %errorlevel% == 0 (
    echo [WEBHOOK] http://localhost:%WEBHOOK_PORT%/status
    type webhook_status.json | findstr /V "^$" | findstr /C:"version" /C:"status" /C:"stats"
    del webhook_status.json
) else (
    echo [WEBHOOK] Not responding
)
echo.

REM TV Agent
curl -s http://localhost:%TV_AGENT_PORT%/health > tv_status.json 2>nul
if %errorlevel% == 0 (
    echo [TV AGENT] http://localhost:%TV_AGENT_PORT%/health
    type tv_status.json | findstr /V "^$"
    del tv_status.json
) else (
    echo [TV AGENT] Not responding
)
echo.

REM TradingView Desktop
echo [TRADINGVIEW DESKTOP]
curl -s http://localhost:9222/json/version > tv_desktop.json 2>nul
if %errorlevel% == 0 (
    echo   Status: Browser responding (CDP enabled)
    type tv_desktop.json | findstr "Browser"
    del tv_desktop.json
) else (
    echo   Status: NOT RESPONDING
    echo   ACTION: Start TradingView Desktop with --remote-debugging-port=9222
)
echo.

REM Ollama
echo [OLLAMA AI]
curl -s http://localhost:11434/api/tags > ollama_status.json 2>nul
if %errorlevel% == 0 (
    echo   Status: Running
    type ollama_status.json | findstr /C:"name" | head -3
    del ollama_status.json
) else (
    echo   Status: NOT RESPONDING
)
echo.

goto end

:view_logs
echo.
echo ===============================================================
echo  VIEW LOGS
echo ===============================================================
echo.
echo  1. Webhook Receiver logs
echo  2. TV Agent logs
echo  3. System processes
echo  0. Back
echo.
set /p log_choice="Enter choice: "

if "%log_choice%"=="1" (
    echo.
    echo [Recent Webhook Logs]
    echo Log file: %WEBHOOK_DIR%\webhook.log
    if exist "%WEBHOOK_DIR%\webhook.log" (
        type "%WEBHOOK_DIR%\webhook.log" | tail -20
    ) else (
        echo No log file found
    )
)

if "%log_choice%"=="2" (
    echo.
    echo [TV Agent Process Info]
    tasklist | findstr "uvicorn"
    tasklist | findstr "python"
)

if "%log_choice%"=="3" (
    echo.
    echo [Python Processes]
    tasklist | findstr "python"
    echo.
    echo [Network Listeners]
    netstat -ano | findstr ":%WEBHOOK_PORT%\|:%TV_AGENT_PORT%"
)

goto end

:end
echo.
echo ===============================================================
echo  Operation complete
echo ===============================================================
echo.
pause
