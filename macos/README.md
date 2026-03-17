# Sapphire Operator Companion - macOS Menu Bar App

A native macOS menu bar app for monitoring your Sapphire platform using canonical `/api/platform/*` contracts.

## Features

### Menu Bar Integration
- 💎/💠/⚠️ health icon based on platform + readiness
- 📊 PM/organization summary (projects, workspaces, agents)
- 📡 Trading summary (signals, trades, PnL, BTC)
- 🛰️ Scout status (sandbox/hook readiness, registration state, dispatch mode)
- 🧾 Latest activity line from platform logs
- 🔄 Auto-refresh every 30 seconds

### Quick Actions
- 🌐 Open Platform (Public)
- 🏢 Open Organization (Public)
- 🧠 Open Intelligence (Public)
- 📡 Open Activity (Public)
- ✅ Open Readiness (Public)
- 🛰️ Open Scout Control (Internal)
- 📡 Open Scout Status (Internal)
- 🔬 Open Scout Sandbox (Internal)
- 📋 Open PM Hub (Internal)
- 🗂️ Open AI PM Manager (Internal)
- 🔧 Infra SSH helpers (RARI1/RARI2/Windows)

## Two Versions

### 1. Python Version (Quick Start)
**Best for:** Immediate use, easy modification

```bash
cd Sapphire/macos/SapphireCommander
pip install -r requirements.txt
python3 sapphire_commander.py
```

`sapphire_commander.py` now launches the updated `sapphire_commander_v2.py` implementation.

### 2. Swift Version (Native)
**Best for:** Production use, native macOS experience

```bash
cd Sapphire/macos/SapphireCommanderNative
open SapphireCommander.xcodeproj
```

Build and run in Xcode. Requires macOS 14.0+

## Configuration

Edit URLs in source if needed, then set optional auth credentials (required when platform APIs are protected by Basic Auth):

```python
# Python version - sapphire_commander_v2.py
CONFIG = {
    "base_url": "https://sapphirealpha.xyz",
    "operator_paths": {
        "home": "/",
        "organization": "/organization",
        "intelligence": "/intelligence",
        "activity": "/activity",
        "readiness": "/production-readiness",
        "status_json": "/api/platform/status",
        "contracts_json": "/api/platform/contracts",
    },
    "internal_urls": {
        "pm_hub_org": "https://agentic-pm-hub-267358751314.us-central1.run.app/organization",
        "pm_manager": "https://agentic-pm-hub-267358751314.us-central1.run.app/organization",
        "scout_status": "https://sapphire-alpha-267358751314.us-central1.run.app/forum/scout/status",
        "scout_control": "https://sapphire-openclaw-cloud-s77j6bxyra-uc.a.run.app",
        "scout_sandbox_health": "https://sapphire-scout-sandbox-s77j6bxyra-uc.a.run.app/health",
    },
    "rari1_ip": "100.120.191.1",
    "rari2_ip": "100.87.225.89",
    "windows_ip": "100.71.10.48",
}
```

```swift
// Swift version - StatusBarController.swift
private let baseURL = "https://sapphirealpha.xyz"
```

```bash
# Optional (Python + Swift runtime support)
export SAPPHIRE_OPERATOR_USER="sapphire"
export SAPPHIRE_OPERATOR_PASSWORD="your-password"
```

Swift app also supports credentials in `UserDefaults`:
- `SapphireOperatorUser`
- `SapphireOperatorPassword`

## Status Icons

| Icon | Meaning |
|------|---------|
| 💎 | Services healthy and readiness green |
| 💠 | Partial degradation / watch state |
| ⚠️ | Degraded health |
| ❌ | Cannot connect to platform API |

## Auto-Start on Login (Python Version)

To start automatically when you log in:

1. Open System Settings → General → Login Items
2. Click "+" and add `sapphire_commander.py`
3. Or use a launch agent:

```bash
cat > ~/Library/LaunchAgents/com.sapphire.commander.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sapphire.commander</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/aribs/Sapphire/macos/SapphireCommander/sapphire_commander.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.sapphire.commander.plist
```

## Keyboard Shortcuts

- `⌘D` - Open Dashboard
- `⌘P` - Open PM Hub
- `⌘M` - Open AI PM Manager
- `⌘R` - Open Readiness
- `⌘A` - Open Activity
- `⌘I` - Open Intelligence
- `⌘Q` - Quit

## Requirements

### Python Version
- Python 3.8+
- macOS 10.14+
- Dependencies: rumps, requests

### Swift Version
- macOS 14.0+
- Xcode 15.0+
- Swift 5.9+

## Troubleshooting

### "No module named rumps"
```bash
pip3 install rumps
```

### "Cannot connect to sapphirealpha.xyz"
- Check your internet connection
- Verify sapphirealpha.xyz is accessible in browser
- Check firewall settings

### SSH not working
- Ensure Terminal.app has permissions
- Verify SSH keys are set up for rari@<ip>
- Test SSH manually: `ssh rari@100.120.191.1`

## Building for Distribution (Swift)

1. Open project in Xcode
2. Select Product → Archive
3. Distribute App → Copy App
4. Share the .app bundle

## Why This Is Better Than a Web Viewer

1. **Always visible** - Menu bar is always accessible
2. **No browser needed** - Quick actions without opening browser
3. **Native SSH** - One-click SSH to infra nodes
4. **System notifications** - Can add native macOS notifications
5. **Offline detection** - Shows ❌ when disconnected
6. **Lower resource usage** - No full browser engine
7. **Keyboard shortcuts** - Quick access without mouse
