# Kimi-Claw on Windows + Pi via Dock

## Setup Overview

```
Internet ←→ Wi-Fi ←→ Windows Laptop (Kimi Master) ←[USB-C Dock]→ Pi (Slave)
```

Your Mac stays separate with its own Kimi installation.

## Step 1: Install Kimi CLI on Windows

On the Windows laptop, open PowerShell as Administrator:

```powershell
# Install Python if not installed
# Download from: https://python.org

# Install Kimi CLI
pip install kimi-cli

# Login to Kimi
kimi login

# Verify installation
kimi info
```

## Step 2: Enable Internet Sharing on Windows

1. Open **Settings → Network & Internet → Mobile Hotspot**
2. OR use Ethernet sharing:
   - Open **Network Connections** (ncpa.cpl)
   - Right-click Wi-Fi adapter → Properties → Sharing tab
   - Check "Allow other network users to connect"
   - Select the USB Ethernet adapter (dock)

## Step 3: Find the Pi's IP

On Windows PowerShell:

```powershell
# Check ARP table
arp -a

# Look for entries on the shared network (usually 192.168.137.x or 192.168.2.x)

# Or scan the network
for ($i=1; $i -lt 255; $i++) {
    Test-Connection -ComputerName "192.168.137.$i" -Count 1 -ErrorAction SilentlyContinue | Where-Object {$_.StatusCode -eq 0}
}
```

## Step 4: SSH to the Pi

```powershell
# Default Pi credentials (if not changed)
ssh pi@192.168.137.xxx
# Password: raspberry

# Or if you changed the password:
ssh pi@192.168.137.xxx
# Enter your password
```

## Step 5: Setup Distributed Kimi-Claw

On the Windows laptop:

### Create config directory
```powershell
mkdir %USERPROFILE%\.kimi\distributed\master
mkdir %USERPROFILE%\.kimi\distributed\slave
```

### Create nodes.json
Create file: `%USERPROFILE%\.kimi\distributed\master\nodes.json`

```json
{
  "slaves": [
    {
      "node_id": "pi-dock-slave",
      "host": "192.168.137.xxx",
      "ssh_user": "pi",
      "max_tasks": 2
    }
  ],
  "master": {
    "local_task_threshold": 0.7,
    "heartbeat_interval": 30,
    "task_timeout": 300
  }
}
```

Replace `192.168.137.xxx` with the Pi's actual IP.

### Copy slave script to Pi

```powershell
# Download/copy kimi_slave.py to Pi
scp kimi_slave.py pi@192.168.137.xxx:~/.kimi/distributed/slave/
```

On the Pi:
```bash
mkdir -p ~/.kimi/distributed/slave ~/.kimi/logs
chmod +x ~/.kimi/distributed/slave/kimi_slave.py
```

## Step 6: Test Connection

On Windows:

```powershell
# Test SSH connectivity
ssh pi@192.168.137.xxx "python3 ~/.kimi/distributed/slave/kimi_slave.py --info"
```

## Step 7: Use Kimi-Claw

On Windows:

```powershell
# Interactive mode
kimi --config-file %USERPROFILE%\.kimi\kimi-claw-distributed.toml

# Or use the wrapper (create this batch file)
```

## Create Windows Wrapper (kimi-claw.bat)

Create `kimi-claw.bat` on your desktop:

```batch
@echo off
set KIMI_CONFIG=%USERPROFILE%\.kimi\kimi-claw-distributed.toml
kimi --config-file %KIMI_CONFIG% %*
```

## Quick Test

1. Open PowerShell
2. Run: `kimi-claw --yes --prompt "Check cluster status"`
3. It should show the Pi as connected

## Troubleshooting

### Can't find Pi IP
```powershell
# Install nmap for Windows and scan
nmap -sn 192.168.137.0/24
```

### SSH fails
- Make sure SSH is enabled on Pi: `sudo raspi-config` → Interface Options → SSH
- Check Windows Firewall allows SSH

### Pi has no internet
- Verify Windows Internet Sharing is enabled
- Check if Pi can ping: `ping 8.8.8.8`

### Kimi command not found
```powershell
# Add to PATH if needed
$env:Path += ";C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\Scripts"
```

## Network Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    OLD WINDOWS LAPTOP                        │
│  ┌──────────┐         ┌──────────────┐                      │
│  │ Kimi CLI │◄───────►│ Distributed  │                      │
│  │  Master  │         │ Orchestrator │                      │
│  └──────────┘         └──────┬───────┘                      │
│         ▲                    │                              │
│         │                    │ SSH                          │
│    Wi-Fi│                    ▼                              │
│  ┌──────┴──────┐    ┌──────────────┐                        │
│  │   Internet  │    │  Raspberry   │                        │
│  └─────────────┘    │     Pi       │                        │
│                     │   (Slave)    │                        │
│                     └──────────────┘                        │
│                           ▲                                 │
│                           │ USB-C Dock Ethernet             │
└───────────────────────────┴─────────────────────────────────┘
```

## Commands Summary

| Task | Command |
|------|---------|
| Find Pi IP | `arp -a` |
| SSH to Pi | `ssh pi@192.168.137.xxx` |
| Test slave | `ssh pi@IP "python3 ~/.kimi/distributed/slave/kimi_slave.py --info"` |
| Check cluster | `kimi --config-file .\kimi-claw-distributed.toml --yes --prompt "check cluster status"` |
| Start bot | `python telegram_kimi_bot.py` |
