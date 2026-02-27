# Sapphire Trading System - Operational Status

**Last Updated:** 2026-02-26  
**Status:** 🟢 OPERATIONAL

---

## 🎯 System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    SAPPHIRE TRADING SYSTEM                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🖥️  WINDOWS PC (100.71.10.48)                                    │
│  ├─ ✅ Webhook Receiver (9090) - RECEIVING SIGNALS               │
│  ├─ ✅ TV Agent (8081) - CONTROLLING TV DESKTOP                  │
│  ├─ ✅ Ollama AI (11434) - 3 MODELS LOADED                       │
│  └─ ⚠️  TradingView Desktop - NEEDS DEBUG PORT                   │
│                                                                  │
│  🥧 PI CLUSTER                                                    │
│  ├─ ✅ rari1 (100.120.191.1) - Controller/Workbench              │
│  └─ ✅ rari2 (100.87.225.89) - Trading Engine                    │
│     ├─ Lighter Bot (18888) - VPN: Switzerland                    │
│     ├─ Trading Engine (18890) - Active                           │
│     └─ Monitoring (18889) - Active                               │
│                                                                  │
│  ☁️  CLOUD SERVICES                                               │
│  ├─ ✅ Command Deck - https://sapphirealpha.xyz                  │
│  ├─ ✅ API Gateway - https://gateway.sapphirealpha.xyz           │
│  └─ ✅ Log Viewer - https://sapphire-log-viewer...               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ Services Status

| Service | Location | Status | URL |
|---------|----------|--------|-----|
| Webhook Receiver | Windows PC | ✅ Online | http://100.71.10.48:9090 |
| TV Agent | Windows PC | ✅ Online | http://100.71.10.48:8081 |
| Ollama AI | Windows PC | ✅ Online | http://localhost:11434 |
| RARI1 Controller | Pi | ✅ Online | http://100.120.191.1:8080 |
| RARI2 Trading | Pi | ✅ Online | http://100.87.225.89:18888 |
| Command Deck | Cloud Run | ✅ Online | https://sapphirealpha.xyz |
| API Gateway | Cloud Run | ✅ Online | https://gateway.sapphirealpha.xyz |

---

## 🔧 Remaining Setup

### 1. TradingView Desktop (Windows)

**Status:** ⚠️ Needs configuration

**Action Required:**
1. Right-click TradingView Desktop shortcut
2. Properties → Target:
   ```
   "C:\Users\<username>\AppData\Local\Packages\...\TradingView.exe" --remote-debugging-port=9222
   ```
3. Start TradingView Desktop
4. Verify: `curl http://localhost:9222/json/version`

### 2. TV Agent → Pi Connection

**Status:** ⚠️ Needs verification

**Test Command:**
```bash
# From Windows PowerShell
curl http://100.87.225.89:18888/status
```

---

## 📡 Signal Flow

```
TradingView Alert
       ↓
[Webhook Receiver:9090] ← Windows PC
       ↓
[Pub/Sub Topic] ← GCP
       ↓
[Pi Trading Engine] ← rari2
       ↓
[Lighter/Drift DEX] ← Execution
```

**Alternative Flow (Direct):**
```
TV Agent (automation)
       ↓
[Sapphire Bridge]
       ↓
[Pi Trading Engine] ← Direct HTTP
       ↓
[DEX Execution]
```

---

## 🎮 API Endpoints

### Windows PC

| Endpoint | Method | Description |
|----------|--------|-------------|
| `http://100.71.10.48:9090/webhook/tradingview` | POST | Receive TradingView alerts |
| `http://100.71.10.48:9090/status` | GET | Webhook status |
| `http://100.71.10.48:8081/health` | GET | TV Agent health |
| `http://100.71.10.48:8081/tv/connect` | POST | Connect to TV Desktop |
| `http://100.71.10.48:8081/tv/symbol/{symbol}` | POST | Change chart symbol |
| `http://100.71.10.48:8081/signals/send` | POST | Send signal to Sapphire |

### Pi Cluster

| Endpoint | Description |
|----------|-------------|
| `http://100.87.225.89:18888/status` | Lighter Bot status |
| `http://100.87.225.89:18890/health` | Trading Engine health |

---

## 🧪 Testing Commands

### From This Mac

```bash
# Test Webhook
curl http://100.71.10.48:9090/status

# Test TV Agent
curl http://100.71.10.48:8081/health

# Test Pi Trading
curl http://100.87.225.89:18888/status

# Send test signal
curl -X POST http://100.71.10.48:9090/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"symbol":"SOLUSDT","action":"buy","price":145.20,"confidence":0.85}'
```

### From Windows PC

```powershell
# Test Pi connectivity
curl http://100.87.225.89:18888/status

# Test TV Desktop
curl http://localhost:9222/json/version
```

---

## 📊 Current Metrics

| Metric | Value |
|--------|-------|
| Signals Processed (24h) | 0 |
| Webhook Uptime | 100% |
| TV Agent Uptime | Just Started |
| Pi Cluster Uptime | 8+ days |
| Ollama Models | 3 loaded |
| Active Trading Bots | 1 (Lighter) |

---

## 🚀 Next Actions

1. **[Windows]** Configure TradingView Desktop with `--remote-debugging-port=9222`
2. **[Windows]** Test TV Agent → TV Desktop connection
3. **[Any]** Send test signal through full pipeline
4. **[Mac]** Run continuous monitoring: `python scripts/monitor_and_alert.py`
5. **[Browser]** Access Command Deck: https://sapphirealpha.xyz

---

## 🔐 Security

- Tailscale VPN: All devices connected
- Windows Firewall: Ports 8081, 9090 open
- Pi Authentication: Key-based SSH
- Cloud Run: HTTPS with SSL

---

## 📞 Support

| Component | Check Command |
|-----------|---------------|
| Webhook | `curl http://100.71.10.48:9090/status` |
| TV Agent | `curl http://100.71.10.48:8081/health` |
| Pi Trading | `curl http://100.87.225.89:18888/status` |
| All | `python scripts/monitor_system.py` |

---

**System Version:** 2.0.0  
**Last Deploy:** 2026-02-26  
**Status:** Ready for Trading
