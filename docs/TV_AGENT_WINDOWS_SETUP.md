# TradingView Agent - Windows PC Setup

## Quick Recovery Check

Since the terminal crashed on Windows, check if your files exist:

```powershell
# On Windows PC, open PowerShell as Administrator
Test-Path C:\TradingViewAutonomousManager
Test-Path C:\sapphire\tv-agent
Test-Path D:\TradingViewAutonomousManager

# If any of these return True, your code is there!
```

## If Files Exist - Restart the Agent

```powershell
# Navigate to your project directory
cd C:\TradingViewAutonomousManager\backend  # or wherever it is

# Activate virtual environment
.\venv\Scripts\activate

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8081
```

## If Files Are Lost - Quick Redeploy

Since I have the code, here are 3 ways to get it back:

### Option 1: Download from GitHub (Recommended)
```powershell
# Open PowerShell
mkdir C:\TradingViewAutonomousManager
cd C:\TradingViewAutonomousManager

# Clone from your repo (if pushed)
git clone https://github.com/arigatoexpress/Sapphire.git temp
Copy-Item temp\services\workbench\TradingViewAutonomousManager\* . -Recurse
Remove-Item temp -Recurse -Force
```

### Option 2: SCP from Mac
```bash
# On this Mac
scp -r /Users/aribs/TradingViewAutonomousManager admin@100.71.10.48:C:/
```

### Option 3: Recreate Fresh
I've saved the complete project. Just tell me and I'll generate a zip for you.

## Windows Service Setup (Auto-start)

Create a Windows service so it auto-starts:

```powershell
# Create a batch file for startup
$startupScript = @"
@echo off
cd /d C:\TradingViewAutonomousManager\backend
call .\venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8081
"@

$startupScript | Out-File -FilePath "C:\TradingViewAutonomousManager\start.bat" -Encoding ASCII

# Create scheduled task for auto-start
$action = New-ScheduledTaskAction -Execute "C:\TradingViewAutonomousManager\start.bat"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "TVAutonomousManager" -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest
```

## TradingView Desktop Prerequisites

On your Windows PC:

1. **Install TradingView Desktop** from Microsoft Store or tradingview.com

2. **Enable Remote Debugging**:
   - Right-click TradingView Desktop shortcut
   - Properties → Target:
   ```
   "C:\Users\<user>\AppData\Local\Packages\TradingView.Desktop_...
   TradingView.exe" --remote-debugging-port=9222
   ```

3. **Start TradingView Desktop**

4. **Verify Connection**:
   ```powershell
   curl http://localhost:9222/json/version
   ```

## API Access

Once running on Windows PC (100.71.10.48):

| Endpoint | URL |
|----------|-----|
| API | http://100.71.10.48:8081 |
| TV Connect | POST http://100.71.10.48:8081/tv/connect |
| Health | GET http://100.71.10.48:8081/health |

## Integration with Sapphire

The agent connects to your Pi cluster:
- Webhook URL: `http://100.87.225.89:8080/tradingview/webhook`
- Gateway URL: `https://sapphire-gateway-267358751314.us-central1.run.app`

Your Windows PC (100.71.10.48) → Pi rari2 (100.87.225.89) → Trading execution

## Troubleshooting

### Port 8081 in use
```powershell
# Find process using port 8081
netstat -ano | findstr :8081

# Kill it
Stop-Process -Id <PID>
```

### Playwright/Chromium issues
```powershell
cd C:\TradingViewAutonomousManager\backend
.\venv\Scripts\activate
playwright install chromium
```

### Can't connect to TradingView Desktop
1. Ensure TV Desktop is running with `--remote-debugging-port=9222`
2. Check Windows Firewall (allow port 9222 locally)
3. Verify TV Desktop is logged in

## What's Running Where

| Component | Location | IP |
|-----------|----------|-----|
| TradingView Agent | Windows PC | 100.71.10.48:8081 |
| TradingView Desktop | Windows PC | localhost:9222 |
| Webhook Receiver | Windows PC | 100.71.10.48:9090 |
| Pi Trading Engine | rari2 | 100.87.225.89:8080 |
| Command Deck | Cloud Run | sapphirealpha.xyz |

---

**Next Step**: Check if your files exist on Windows, then restart the agent. If files are gone, let me know and I'll help you redeploy!
