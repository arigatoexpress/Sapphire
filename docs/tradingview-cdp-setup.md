# TradingView Desktop — CDP Setup Guide
**Target:** Windows PC (100.x.x.z, user: aribs)  
**Goal:** Enable Chrome DevTools Protocol on port 9222 for TradingView MCP

---

## Current State (2026-04-14)

| Item | Status |
|------|--------|
| TradingView Desktop installed | ✅ Running (MSIX/Store package) |
| Package | `TradingView.Desktop_3.0.0.7652_x64__n534cwy3pjxzj` |
| Application ID | `TradingView.Desktop` |
| Executable | `C:\Program Files\WindowsApps\TradingView.Desktop_3.0.0.7652_x64__n534cwy3pjxzj\TradingView.exe` |
| Port 9222 open | ❌ Not yet — TradingView running without CDP flag |
| Firewall rule | ✅ Added (`TradingView CDP`, TCP inbound 9222) |
| Desktop launcher | ✅ `C:\Users\aribs\Desktop\TradingView-CDP.bat` created |
| Mac MCP server | ✅ `/opt/homebrew/bin/tv` installed |

---

## Step 1: Enable CDP on Windows (one-time manual step)

A launcher script is already on your Windows desktop:  
**`C:\Users\aribs\Desktop\TradingView-CDP.bat`**

**Double-click it.** It will:
1. Kill the running TradingView instance
2. Wait 4 seconds
3. Relaunch TradingView with `--remote-debugging-port=9222`

After ~10 seconds, verify CDP is active in Windows PowerShell:
```powershell
netstat -an | findstr 9222
# Should show: TCP  0.0.0.0:9222  ...  LISTENING
```

Or verify from Mac:
```bash
curl http://100.x.x.z:9222/json
# Should return a JSON array of tabs
```

---

## Step 2: Persist CDP Launch on Startup

The MSIX app can't be added to startup via registry (UWP package restrictions). Best options:

### Option A: Windows Startup Folder (simplest)
1. Press `Win+R`, type `shell:startup`, press Enter
2. Copy `TradingView-CDP.bat` from Desktop into the Startup folder
3. TradingView will now launch with CDP on every login

### Option B: Task Scheduler (already attempted via SSH — may need admin)
```cmd
schtasks /create /tn "TradingView-CDP" ^
  /tr "\"C:\Program Files\WindowsApps\TradingView.Desktop_3.0.0.7652_x64__n534cwy3pjxzj\TradingView.exe\" --remote-debugging-port=9222" ^
  /sc onlogon /rl highest /f
```
Run in an elevated (Admin) PowerShell if the above fails.

---

## Step 3: Mac MCP Server Setup

The tradingview-mcp v2 server is already installed at `/opt/homebrew/bin/tv`.

### Add to Claude Code MCP config
Edit `~/.claude/settings.json` and add under `mcpServers`:
```json
{
  "mcpServers": {
    "tradingview-mcp": {
      "command": "node",
      "args": ["/Users/aribs/Code/tradingview-mcp-v2/src/server.js"],
      "env": {
        "CDP_HOST": "100.x.x.z",
        "CDP_PORT": "9222"
      }
    }
  }
}
```

The MCP server connects to `http://{CDP_HOST}:{CDP_PORT}/json/list` to find the TradingView chart tab.

### Test the connection
Once TradingView has CDP enabled:
```bash
tv status                    # Should show: CDP connected, N tabs, M TradingView tabs
tv quote --symbol BTCUSDT    # Live price
tv get-indicators            # List active indicators
```

---

## Step 4: Verify End-to-End

From Mac, after Windows CDP is enabled:
```bash
# Test CDP directly
curl -s http://100.x.x.z:9222/json | python3 -c "
import json, sys
tabs = json.load(sys.stdin)
tv = [t for t in tabs if 'tradingview' in t.get('url','').lower()]
print(f'Total tabs: {len(tabs)}, TradingView tabs: {len(tv)}')
for t in tv: print(f'  {t[\"title\"]} — {t[\"url\"][:60]}')
"

# Dashboard CDP status
curl -su "sapphire:sapphire" http://127.0.0.1:8080/api/system | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('CDP:', d.get('cdp'))"
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port 9222 not listening after bat run | MSIX app may ignore CLI args — see Alternative below |
| `curl 100.x.x.z:9222` times out from Mac | Firewall rule not applied — run bat as Admin or check Tailscale routing |
| TradingView starts but no chart tab | Log into TradingView, open a chart; CDP needs a live chart to expose TV tab |
| MCP connects but tools fail | TV Desktop may need to be on a chart page (not screener/watchlist) |

### Alternative if MSIX rejects `--remote-debugging-port`
Some MSIX-packaged Electron apps don't pass CLI args through the MSIX activation layer. If the flag is silently dropped:

1. **Check if a standalone installer exists** at `tradingview.com/desktop` — the non-Store version accepts all Electron flags
2. **Use the `electron-flags` approach**: some MSIX apps read from `%APPDATA%\TradingView\electron-flags.cfg` — create this file with `--remote-debugging-port=9222` on its own line

---

## Architecture (once running)

```
Claude Code (Mac)
    └── tradingview-mcp v2 (node, stdio)
            └── chrome-remote-interface
                    └── CDP http://100.x.x.z:9222
                            └── TradingView Desktop (Electron, Windows)
                                    └── Chart: BTCUSDT, indicators, Pine editor
```

The MCP server exposes 68 tools including:
- `tv_get_quote` — live prices
- `tv_get_indicators` — active indicator values (RSI, MACD, BB, etc.)
- `tv_capture_chart` — screenshot
- `tv_pine_write` / `tv_pine_compile` — Pine Script automation
- `tv_create_alert` — programmatic alerts
- `tv_read_chart_data` — OHLCV + drawing data
