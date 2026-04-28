# Kimi-Claw Windows + Pi Setup Script
# Run this in PowerShell as Administrator

Write-Host "🚀 Setting up Kimi-Claw on Windows with Pi Slave" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "⚠️  Please run this script as Administrator" -ForegroundColor Yellow
}

# Step 1: Check Kimi installation
Write-Host "`n📦 Checking Kimi CLI..." -ForegroundColor Blue
$kimi = Get-Command kimi -ErrorAction SilentlyContinue
if (-not $kimi) {
    Write-Host "❌ Kimi CLI not found. Installing..." -ForegroundColor Red
    Write-Host "Running: pip install kimi-cli"
    pip install kimi-cli
} else {
    Write-Host "✅ Kimi found: $(kimi --version)" -ForegroundColor Green
}

# Step 2: Check Kimi auth
Write-Host "`n🔐 Checking Kimi authentication..." -ForegroundColor Blue
$kimiAuth = kimi info 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Kimi is authenticated" -ForegroundColor Green
} else {
    Write-Host "⚠️  Kimi not authenticated. Run: kimi login" -ForegroundColor Yellow
}

# Step 3: Create directories
Write-Host "`n📁 Creating directories..." -ForegroundColor Blue
$kimiDir = "$env:USERPROFILE\.kimi"
$distributedDir = "$kimiDir\distributed\master"
$slaveDir = "$kimiDir\distributed\slave"

New-Item -ItemType Directory -Force -Path $distributedDir | Out-Null
New-Item -ItemType Directory -Force -Path $slaveDir | Out-Null

Write-Host "✅ Directories created" -ForegroundColor Green

# Step 4: Create distributed config
Write-Host "`n⚙️  Creating configuration files..." -ForegroundColor Blue

$kimiClawConfig = @"
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
You are Kimi-Claw, the unified AI agent.
You have access to a Raspberry Pi slave node via distributed computing.

Your slave node can handle:
- CPU-intensive tasks
- Parallel processing
- Long-running computations

Use it wisely for tasks that would benefit from offloading.
"""

[agent.skills]
extra_dirs = [
    "~/.codex/skills/kimi-claw",
    "~/.codex/skills/sapphire-agent"
]
"@

$kimiClawConfig | Out-File -FilePath "$kimiDir\kimi-claw-distributed.toml" -Encoding UTF8
Write-Host "✅ Created kimi-claw-distributed.toml" -ForegroundColor Green

# Step 5: Find Pi
Write-Host "`n🔍 Searching for Raspberry Pi on network..." -ForegroundColor Blue
Write-Host "Checking ARP table for potential Pi addresses..." -ForegroundColor Gray

# Get all ARP entries
$arpEntries = arp -a | Select-String "192\.168\.(137|2)\.|10\.0\.0\."

if ($arpEntries) {
    Write-Host "`nPotential Pi addresses found:" -ForegroundColor Green
    $arpEntries | ForEach-Object { Write-Host "  $_" }

    # Check SSH on each
    Write-Host "`nTesting SSH connectivity..." -ForegroundColor Blue
    foreach ($entry in $arpEntries) {
        if ($entry -match "\((\d+\.\d+\.\d+\.\d+)\)") {
            $ip = $matches[1]
            $test = Test-NetConnection -ComputerName $ip -Port 22 -WarningAction SilentlyContinue
            if ($test.TcpTestSucceeded) {
                Write-Host "  ✅ SSH open on $ip" -ForegroundColor Green

                # Create nodes.json with this IP
                $nodesConfig = @"
{
  "slaves": [
    {
      "node_id": "pi-dock-slave",
      "host": "$ip",
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
"@
                $nodesConfig | Out-File -FilePath "$distributedDir\nodes.json" -Encoding UTF8
                Write-Host "  ✅ Created nodes.json with IP: $ip" -ForegroundColor Green
            } else {
                Write-Host "  ❌ No SSH on $ip" -ForegroundColor Gray
            }
        }
    }
} else {
    Write-Host "⚠️  No Pi found on common shared network subnets" -ForegroundColor Yellow
    Write-Host "   Make sure:" -ForegroundColor Yellow
    Write-Host "   1. Pi is connected to the dock's Ethernet" -ForegroundColor Yellow
    Write-Host "   2. Internet Sharing is enabled on Windows" -ForegroundColor Yellow
    Write-Host "   3. Pi has booted up (wait for green LED to stop blinking)" -ForegroundColor Yellow
}

# Step 6: Test
Write-Host "`n🧪 Testing setup..." -ForegroundColor Blue

if (Test-Path "$distributedDir\nodes.json") {
    Write-Host "✅ Configuration files ready" -ForegroundColor Green
    Write-Host "`nNext steps:" -ForegroundColor Cyan
    Write-Host "1. Copy slave script to Pi:" -ForegroundColor White
    Write-Host "   scp kimi_slave.py pi@IP:~/.kimi/distributed/slave/" -ForegroundColor Gray
    Write-Host "`n2. Test connection:" -ForegroundColor White
    Write-Host "   ssh pi@IP 'python3 ~/.kimi/distributed/slave/kimi_slave.py --info'" -ForegroundColor Gray
    Write-Host "`n3. Start using Kimi-Claw:" -ForegroundColor White
    Write-Host "   kimi --config-file %USERPROFILE%\.kimi\kimi-claw-distributed.toml" -ForegroundColor Gray
} else {
    Write-Host "⚠️  Setup incomplete - Pi not detected" -ForegroundColor Yellow
    Write-Host "   Run this script again after Pi is connected and sharing is enabled" -ForegroundColor Yellow
}

Write-Host "`n================================================" -ForegroundColor Cyan
Write-Host "Setup complete!" -ForegroundColor Cyan
