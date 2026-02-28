@echo off
setlocal EnableDelayedExpansion
echo ===============================================================
echo  SAPPHIRE SERVICES - AUTO-START INSTALLER
echo ===============================================================
echo.
echo This will configure Windows to automatically start:
echo   - Webhook Receiver (port 9090)
echo   - TV Agent (port 8081)
echo.
echo Run as Administrator for best results.
echo.
pause

echo.
echo [Step 1/4] Creating startup scripts...
echo.

REM Create directory for logs
if not exist "C:\sapphire\logs" mkdir "C:\sapphire\logs"

REM Create Webhook startup script
(
echo @echo off
echo cd /d "C:\sapphire\services\workbench\tradingview"
echo python webhook_receiver.py ^>^> C:\sapphire\logs\webhook.log 2^>^&1
) > "C:\sapphire\start_webhook.bat"

echo [OK] Created: C:\sapphire\start_webhook.bat

REM Create TV Agent startup script (will be filled with actual path)
set "TV_PATH="
if exist "C:\TradingViewAutonomousManager\backend\main.py" (
    set "TV_PATH=C:\TradingViewAutonomousManager\backend"
) else if exist "C:\sapphire\tv-agent\backend\main.py" (
    set "TV_PATH=C:\sapphire\tv-agent\backend"
) else if exist "%USERPROFILE%\TradingViewAutonomousManager\backend\main.py" (
    set "TV_PATH=%USERPROFILE%\TradingViewAutonomousManager\backend"
)

if defined TV_PATH (
    (
    echo @echo off
    echo cd /d "%TV_PATH%"
    echo call venv\Scripts\activate.bat
    echo uvicorn main:app --host 0.0.0.0 --port 8081 --log-level info ^>^> C:\sapphire\logs\tv_agent.log 2^>^&1
    ) > "C:\sapphire\start_tv_agent.bat"
    echo [OK] Created: C:\sapphire\start_tv_agent.bat
) else (
    echo [WARN] TV Agent not found - skipping TV Agent auto-start
    echo        You can add it manually later.
)

echo.
echo [Step 2/4] Creating Windows Task Scheduler jobs...
echo.

REM Webhook Task
schtasks /create /tn "SapphireWebhook" /tr "C:\sapphire\start_webhook.bat" /sc onstart /ru SYSTEM /rl HIGHEST /f 2>nul
if %errorlevel% == 0 (
    echo [OK] Created task: SapphireWebhook
) else (
    echo [INFO] Task SapphireWebhook already exists or requires admin rights
    echo        Run as Administrator to create tasks.
)

REM TV Agent Task
if exist "C:\sapphire\start_tv_agent.bat" (
    schtasks /create /tn "SapphireTVAgent" /tr "C:\sapphire\start_tv_agent.bat" /sc onstart /ru SYSTEM /rl HIGHEST /f 2>nul
    if %errorlevel% == 0 (
        echo [OK] Created task: SapphireTVAgent
    ) else (
        echo [INFO] Task SapphireTVAgent already exists or requires admin rights
    )
)

echo.
echo [Step 3/4] Creating desktop shortcuts...
echo.

REM Management shortcut
(
echo @echo off
echo cd /d "C:\sapphire"
echo call services\workbench\tradingview\manage_services.bat
) > "%USERPROFILE%\Desktop\Sapphire Services Manager.bat"

echo [OK] Created: Desktop\Sapphire Services Manager.bat

REM Quick start shortcut
(
echo @echo off
echo echo Starting Sapphire TV Agent...
echo call "C:\sapphire\start_tv_agent.bat"
) > "%USERPROFILE%\Desktop\Start TV Agent.bat"

echo [OK] Created: Desktop\Start TV Agent.bat

echo.
echo [Step 4/4] Testing current installation...
echo.

netstat -ano | findstr ":9090" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    echo [OK] Webhook Receiver is currently running
) else (
    echo [INFO] Webhook Receiver not running - will start on next boot
)

netstat -ano | findstr ":8081" | findstr "LISTENING" >nul
if %errorlevel% == 0 (
    echo [OK] TV Agent is currently running
) else (
    echo [INFO] TV Agent not running - will start on next boot
    echo.
    set /p start_now="Start TV Agent now? (y/n): "
    if /I "%start_now%"=="y" (
        call "C:\sapphire\start_tv_agent.bat"
    )
)

echo.
echo ===============================================================
echo  SETUP COMPLETE
echo ===============================================================
echo.
echo Services will auto-start on Windows boot.
echo.
echo To manage manually:
echo   - Desktop\Sapphire Services Manager.bat
echo   - Desktop\Start TV Agent.bat
echo.
echo To start now (as current user):
echo   schtasks /run /tn "SapphireWebhook"
echo   schtasks /run /tn "SapphireTVAgent"
echo.
echo Logs: C:\sapphire\logs\
echo.
pause
