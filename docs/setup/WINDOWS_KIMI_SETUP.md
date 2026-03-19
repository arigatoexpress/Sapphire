# Kimi-Claw Setup on Windows + Pi Slave

## ✅ Current Status
- Windows laptop: Connected to WiFi (has internet)
- Pi: Connected to Windows via Ethernet (dock)
- Goal: Windows as Kimi Master, Pi as Slave

## Network Topology

```
Internet ←→ Wi-Fi ←→ Windows Laptop (Kimi Master)
                            │
                            └── USB-C Dock ←→ Pi (Slave)
                                               192.168.137.x or 192.168.2.x
```

## Step 1: Install Kimi on Windows

Open **PowerShell as Administrator**:

```powershell
# Check if Python is installed
python --version

# If not, install from python.org (check "Add to PATH")

# Install Kimi CLI
pip install kimi-cli

# Login to Kimi
kimi login

# Verify
kimi info
```

## Step 2: Find the Pi's IP

Since Windows has internet sharing or the Pi is on a local subnet:

```powershell
# Check ARP table
arp -a

# Look for entries like:
# - 192.168.137.x (Windows sharing subnet)
# - 192.168.2.x (other sharing subnet)
# - 10.0.0.x

# Or scan common ranges
for ($i=1; $i -lt 255; $i++) {
    Test-Connection -ComputerName "192.168.137.$i" -Count 1 -ErrorAction SilentlyContinue | Where-Object {$_.StatusCode -eq 0}
}
```

## Step 3: Configure SSH on Pi (if not done)

From your Mac, SSH to the Pi:

```bash
ssh pi@PI_WIFI_IP

# Enable SSH if not enabled
sudo raspi-config
# → Interface Options → SSH → Enable

# Or manually:
sudo systemctl enable ssh
sudo systemctl start ssh
```

## Step 4: Setup Distributed Config on Windows

Create the directory structure:

```powershell
mkdir %USERPROFILE%\.kimi\distributed\master
mkdir %USERPROFILE%\.kimi\distributed\slave
```

Create nodes.json:

```powershell
notepad %USERPROFILE%\.kimi\distributed\master\nodes.json
```

Paste (replace with actual Pi IP):
```json
{
  "slaves": [
    {
      "node_id": "pi-ethernet-slave",
      "host": "192.168.137.10",
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

## Step 5: Create Kimi Config

```powershell
notepad %USERPROFILE%\.kimi\kimi-claw-distributed.toml
```

Paste:
```toml
default_model = "kimi-code/kimi-for-coding"
default_thinking = true
default_yolo = false

[models."kimi-code/kimi-for-coding"]
provider = "managed:kimi-code"
model = "kimi-for-coding"
max_context_size = 262144
capabilities = ["thinking", "image_in", "video_in"]

[providers."managed:kimi-code"]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"
api_key = ""

[providers."managed:kimi-code".oauth]
storage = "file"
key = "oauth/kimi-code"

[loop_control]
max_steps_per_turn = 200
max_retries_per_step = 3
max_ralph_iterations = 0
reserved_context_size = 50000

[services.moonshot_search]
base_url = "https://api.kimi.com/coding/v1/search"
api_key = ""

[services.moonshot_search.oauth]
storage = "file"
key = "oauth/kimi-code"

[services.moonshot_fetch]
base_url = "https://api.kimi.com/coding/v1/fetch"
api_key = ""

[services.moonshot_fetch.oauth]
storage = "file"
key = "oauth/kimi-code"

[mcp.client]
tool_call_timeout_ms = 60000

[agent]
name = "Kimi-Claw"
identity = """
You are Kimi-Claw, the unified AI agent with distributed computing capabilities.

You have access to a Raspberry Pi slave node for offloading CPU-intensive tasks.

Use the slave for:
- Large file processing
- Parallel computations
- Long-running tasks

The Pi is accessible via SSH and can execute shell commands and Python code.
"""

[agent.distributed]
enabled = true
config_path = "~/.kimi/distributed/master/nodes.json"
auto_offload = true
local_load_threshold = 0.7
```

## Step 6: Install Slave Script on Pi

From Windows PowerShell:

```powershell
# Create the slave script locally first
# Copy content from Mac's ~/.kimi/distributed/slave/kimi_slave.py

# Then copy to Pi
scp kimi_slave.py pi@192.168.137.10:~/.kimi/distributed/slave/
```

Or create it directly on Pi via SSH:

```bash
# SSH to Pi from Mac
ssh pi@PI_ETHERNET_IP

# Create directories
mkdir -p ~/.kimi/distributed/slave ~/.kimi/logs

# Create the slave script (paste the Python code)
nano ~/.kimi/distributed/slave/kimi_slave.py

# Make executable
chmod +x ~/.kimi/distributed/slave/kimi_slave.py
```

## Step 7: Test Connection

```powershell
# Test SSH
ssh pi@192.168.137.10 "echo 'Pi is reachable'"

# Test slave script
ssh pi@192.168.137.10 "python3 ~/.kimi/distributed/slave/kimi_slave.py --info"
```

## Step 8: Use Kimi-Claw

```powershell
# Interactive mode
kimi --config-file %USERPROFILE%\.kimi\kimi-claw-distributed.toml

# One-shot command
kimi --config-file %USERPROFILE%\.kimi\kimi-claw-distributed.toml --yes --prompt "Check cluster status"

# With auto-approve
kimi --config-file %USERPROFILE%\.kimi\kimi-claw-distributed.toml --yes --prompt "Run a heavy computation task"
```

## Create Batch Wrapper

Create `kimi-claw.bat` on your desktop:

```batch
@echo off
set CONFIG=%USERPROFILE%\.kimi\kimi-claw-distributed.toml

if "%1"=="--status" (
    echo Checking cluster status...
    kimi --config-file %CONFIG% --yes --prompt "List all connected slave nodes and their status"
    goto :eof
)

if "%1"=="--pi" (
    echo Connecting to Pi via SSH...
    ssh pi@192.168.137.10
    goto :eof
)

if "%1"=="--help" (
    echo Kimi-Claw Commands:
    echo   kimi-claw --status    Check cluster status
    echo   kimi-claw --pi        SSH to Pi
    echo   kimi-claw "prompt"    Send prompt to Kimi
    goto :eof
)

kimi --config-file %CONFIG% %*
```

## Quick Commands Reference

| Task | Command |
|------|---------|
| Check status | `kimi-claw --status` |
| SSH to Pi | `kimi-claw --pi` or `ssh pi@192.168.137.10` |
| Run task | `kimi-claw "deploy Sapphire to Cloud Run"` |
| Check cluster | `kimi-claw --yes --prompt "check distributed cluster"` |

## Troubleshooting

### Can't find Pi IP
```powershell
# Try different subnets
arp -a | findstr 192.168
arp -a | findstr 10.0

# Or use nmap if installed
nmap -sn 192.168.137.0/24
```

### SSH fails
- Check Pi SSH is enabled: `sudo systemctl status ssh` (on Pi)
- Check Windows firewall allows SSH client
- Verify Pi password

### Kimi not found
```powershell
# Add Python Scripts to PATH
$env:Path += ";C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\Scripts"
# Or wherever pip installed kimi
```

### Pi can't execute tasks
- Check Python3 is installed on Pi: `python3 --version`
- Check slave script exists: `ls ~/.kimi/distributed/slave/`
- Check permissions: `chmod +x ~/.kimi/distributed/slave/kimi_slave.py`

## Verify Setup

Test everything works:

```powershell
# 1. Kimi is installed
kimi --version

# 2. Can reach Pi
ping 192.168.137.10

# 3. Can SSH to Pi
ssh pi@192.168.137.10 "hostname"

# 4. Slave script works
ssh pi@192.168.137.10 "python3 ~/.kimi/distributed/slave/kimi_slave.py --info"

# 5. Distributed Kimi works
kimi --config-file %USERPROFILE%\.kimi\kimi-claw-distributed.toml --yes --prompt "Check cluster status and list capabilities"
```

All tests should pass! 🎉
