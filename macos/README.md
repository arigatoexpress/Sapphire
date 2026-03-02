# Sapphire Commander - macOS Menu Bar App

A native macOS menu bar app for monitoring and controlling your Sapphire trading infrastructure.

## Features

### Menu Bar Integration
- 💎 Live status icon in menu bar (changes based on system health)
- 📊 Real-time PM project count
- 📡 Active trading signals
- 💰 Live BTC/ETH prices
- 🔄 Auto-refresh every 30 seconds

### Quick Actions
- 🌐 Open sapphirealpha.xyz dashboard
- 📋 Open PM Hub
- 🔧 SSH to RARI1 (opens Terminal)
- ⚡ SSH to RARI2 (opens Terminal)
- 📄 View system logs

## Two Versions

### 1. Python Version (Quick Start)
**Best for:** Immediate use, easy modification

```bash
cd Sapphire/macos/SapphireCommander
pip install -r requirements.txt
python3 sapphire_commander.py
```

The app will appear in your menu bar as 💎

### 2. Swift Version (Native)
**Best for:** Production use, native macOS experience

```bash
cd Sapphire/macos/SapphireCommanderNative
open SapphireCommander.xcodeproj
```

Build and run in Xcode. Requires macOS 14.0+

## Configuration

Edit the URLs in the source to match your setup:

```python
# Python version - sapphire_commander.py
CONFIG = {
    'sapphire_url': 'https://sapphirealpha.xyz',
    'gateway_url': 'https://sapphire-gateway-...',
    'pm_hub_url': 'https://agentic-pm-hub-...',
    'rari1_ip': '100.120.191.1',
    'rari2_ip': '100.87.225.89',
}
```

```swift
// Swift version - StatusBarController.swift
let sapphireURL = "https://sapphirealpha.xyz"
```

## Status Icons

| Icon | Meaning |
|------|---------|
| 💎 | All systems healthy |
| 💠 | Some services degraded (>70% healthy) |
| ⚠️ | Major issues (<70% healthy) |
| ❌ | Cannot connect to sapphirealpha.xyz |

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
- `⌘R` - Refresh Now
- `⌘L` - View Logs
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
3. **Native SSH** - One-click SSH to Pi cluster
4. **System notifications** - Can add native macOS notifications
5. **Offline detection** - Shows ❌ when disconnected
6. **Lower resource usage** - No full browser engine
7. **Keyboard shortcuts** - Quick access without mouse
