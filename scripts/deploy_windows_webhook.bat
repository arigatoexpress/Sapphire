@echo off
REM Sapphire OS - Windows PC Webhook Deployment Script
REM Run this on the Windows PC to deploy the latest webhook receiver

echo ===================================================
echo Sapphire OS - Windows Webhook Deployment
echo ===================================================
echo.

REM Check if running as admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires Administrator privileges.
    echo Please right-click and select "Run as Administrator"
    pause
    exit /b 1
)

set INSTALL_DIR=C:\sapphire
set REPO_URL=https://github.com/arigatoexpress/Sapphire.git

echo [1/5] Checking installation directory...
if not exist "%INSTALL_DIR%" (
    echo Creating %INSTALL_DIR%...
    mkdir "%INSTALL_DIR%"
)

echo [2/5] Downloading latest code from GitHub...
cd "%INSTALL_DIR%"

REM Download specific files via curl
set GITHUB_RAW=https://raw.githubusercontent.com/arigatoexpress/Sapphire/main

echo Downloading webhook_receiver_v2.py...
curl -L -o services\workbench\tradingview\webhook_receiver.py "%GITHUB_RAW%/services/workbench/tradingview/webhook_receiver_v2.py" 2>nul || (
    echo Warning: Could not download webhook receiver
)

echo Downloading logging_config.py...
if not exist "services\shared" mkdir "services\shared"
curl -L -o services\shared\logging_config.py "%GITHUB_RAW%/services/shared/logging_config.py" 2>nul || (
    echo Warning: Could not download logging config
)

echo Downloading requirements...
curl -L -o requirements.txt "%GITHUB_RAW%/requirements.txt" 2>nul || (
    echo Warning: Could not download requirements
)

echo [3/5] Installing/updating Python dependencies...
python -m pip install -q -r requirements.txt 2>nul

echo [4/5] Configuring Windows Task Scheduler...
REM Create task to auto-start webhook receiver on boot
schtasks /query /tn "SapphireWebhook" >nul 2>&1
if %errorLevel% equ 0 (
    echo Task already exists, updating...
    schtasks /delete /tn "SapphireWebhook" /f >nul 2>&1
)

echo Creating scheduled task...
schtasks /create /tn "SapphireWebhook" /tr "python %INSTALL_DIR%\services\workbench\tradingview\webhook_receiver.py" /sc onstart /ru SYSTEM /rl HIGHEST >nul 2>&1

echo [5/5] Starting webhook receiver...
REM Start the service
start /b python "%INSTALL_DIR%\services\workbench\tradingview\webhook_receiver.py" > %INSTALL_DIR%\webhook.log 2>&1

echo.
echo ===================================================
echo Deployment Complete!
echo ===================================================
echo.
echo Webhook receiver is running on port 9090
echo Check logs: %INSTALL_DIR%\webhook.log
echo.
echo Status URL: http://localhost:9090/status
echo Health URL: http://localhost:9090/health
echo.
echo To view in real-time:
echo   tail -f %INSTALL_DIR%\webhook.log
echo.
echo To restart:
echo   schtasks /run /tn "SapphireWebhook"
echo.
pause
