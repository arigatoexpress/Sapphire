# Sapphire Trading System - Quick Start Guide

## 🎉 You're Almost Ready to Trade!

Your system is **OPERATIONAL**. Here's what to do next:

---

## ✅ What's Already Running

### Windows PC (100.71.10.48)
- ✅ **Webhook Receiver** (port 9090) - Receiving signals
- ✅ **TV Agent** (port 8081) - Just started!
- ✅ **Ollama AI** - 3 models ready

### Pi Cluster
- ✅ **rari1** - Controller/Workbench
- ✅ **rari2** - Trading Engine (Lighter Bot active)

### Cloud
- ✅ **Command Deck** - https://sapphirealpha.xyz
- ✅ **Gateway & Logs** - All online

---

## 🚀 Final Setup Steps

### Step 1: Configure TradingView Desktop (2 minutes)

1. **Close** TradingView Desktop if running
2. **Right-click** TradingView shortcut → **Properties**
3. **Modify Target** to add debug port:
   ```
   "C:\Users\...\TradingView.exe" --remote-debugging-port=9222
   ```
4. **Apply** → **OK**
5. **Start** TradingView Desktop

**Verify it's working:**
```powershell
# In PowerShell on Windows
curl http://localhost:9222/json/version
```

### Step 2: Test TV Agent Connection (1 minute)

```powershell
# Connect TV Agent to TradingView Desktop
curl -X POST http://localhost:8081/tv/connect

# Check status
curl http://localhost:8081/tv/state
```

### Step 3: Test Trading Signal (1 minute)

```powershell
# Send test signal through pipeline
curl -X POST http://localhost:9090/webhook/tradingview `
  -H "Content-Type: application/json" `
  -d '{"symbol":"SOLUSDT","action":"buy","price":100,"confidence":0.9}'
```

---

## 📊 Access Your Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| **Command Deck** | https://sapphirealpha.xyz | Main control center |
| **Log Viewer** | https://sapphire-log-viewer-267358751314.us-central1.run.app | System logs |
| **TV Agent** | http://100.71.10.48:8081 | TV automation API |
| **Webhook** | http://100.71.10.48:9090 | Signal receiver |

**Default Login:**
- Username: `sapphire`
- Password: `alpha2024`

---

## 🎮 Common Operations

### Change Chart Symbol via API
```powershell
curl -X POST http://localhost:8081/tv/symbol/BTCUSDT
```

### Check All Services
```powershell
# From this Mac
python scripts/monitor_system.py
```

### View Logs
```powershell
# Windows Webhook logs (if saved)
Get-Content C:\sapphire\logs\webhook.log -Tail 20
```

---

## 🔧 Troubleshooting

### TV Agent won't connect to TradingView
1. Ensure TV Desktop is running with `--remote-debugging-port=9222`
2. Check Windows Firewall allows port 9222
3. Try: `curl http://localhost:9222/json/version`

### Signals not reaching Pi
1. Check Tailscale: `tailscale status`
2. Test Pi connectivity: `curl http://100.87.225.89:18888/status`
3. Check Pub/Sub: `curl http://localhost:9090/status`

### Webhook not receiving
1. Verify port 9090: `netstat -ano | findstr :9090`
2. Check Windows Firewall
3. Restart: Use `manage_sapphire_services.bat`

---

## 📈 Trading Pairs Ready

| Pair | Venue | Type |
|------|-------|------|
| SOLUSDT | ASTER | Perp |
| BTCUSDT | LIGHTER | Perp |
| ETHUSDT | LIGHTER | Perp |
| ETHBTC | LIGHTER | Pair |
| SOLBTC | ASTER | Pair |

---

## 🔄 Auto-Start (Optional)

Run as Administrator on Windows:
```powershell
.\install_autostart.bat
```

This sets up both services to start automatically on Windows boot.

---

## 🎯 You're Ready!

Once TradingView Desktop is configured with the debug port:
1. Create alerts in TradingView
2. Set webhook URL to: `http://100.71.10.48:9090/webhook/tradingview`
3. Watch signals flow to your Pi for execution!

**Happy Trading! 💎🚀**

---

## 📚 More Documentation

- Operational Status <!-- removed: file deleted 2026-03-18 --> - Full system status
- TV Agent Windows Setup <!-- removed: file deleted 2026-03-18 --> - Windows-specific guide
- [Logging](LOGGING.md) - Logging infrastructure
- [GitHub](https://github.com/arigatoexpress/Sapphire) - Full codebase
