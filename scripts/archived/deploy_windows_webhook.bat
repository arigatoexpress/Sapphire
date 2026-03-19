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
if not exist "services\workbench\tradingview" mkdir "services\workbench\tradingview"
if not exist "services\shared" mkdir "services\shared"
if not exist "logs" mkdir "logs"

REM Download specific files via curl
set GITHUB_RAW=https://raw.githubusercontent.com/arigatoexpress/Sapphire/main

echo Downloading webhook_receiver.py...
curl -L -o services\workbench\tradingview\webhook_receiver.py "%GITHUB_RAW%/services/workbench/tradingview/webhook_receiver.py" 2>nul || (
    echo Warning: Could not download webhook receiver
)

echo Downloading logging_config.py...
curl -L -o services\shared\logging_config.py "%GITHUB_RAW%/services/shared/logging_config.py" 2>nul || (
    echo Warning: Could not download logging config
)

echo Downloading webhook requirements...
curl -L -o services\workbench\tradingview\webhook_requirements.txt "%GITHUB_RAW%/services/workbench/tradingview/webhook_requirements.txt" 2>nul || (
    echo Warning: Could not download requirements
)

echo [3/5] Installing/updating Python dependencies...
python -m pip install -q -r services\workbench\tradingview\webhook_requirements.txt 2>nul

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
set WEBHOOK_LOG_FILE=%INSTALL_DIR%\logs\webhook.log
start /b python "%INSTALL_DIR%\services\workbench\tradingview\webhook_receiver.py" > %INSTALL_DIR%\webhook_stdout.log 2>&1

echo.
echo ===================================================
echo Deployment Complete!
echo ===================================================
echo.
echo Webhook receiver is running on port 9090
echo Check logs: %INSTALL_DIR%\logs\webhook.log
echo Stdout log: %INSTALL_DIR%\webhook_stdout.log
echo.
echo Status URL: http://localhost:9090/status
echo Health URL: http://localhost:9090/health
echo.
echo To view in real-time:
echo   powershell -Command "Get-Content -Path %INSTALL_DIR%\logs\webhook.log -Wait"
echo.
echo To restart:
echo   schtasks /run /tn "SapphireWebhook"
echo.
pause
