# Kimi-Claw Windows Setup Script
# Run this in PowerShell as Administrator

Write-Host "🚀 Setting up Kimi-Claw on Windows" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

# Check admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "⚠️  Please run PowerShell as Administrator" -ForegroundColor Yellow
    exit 1
}

# Step 1: Check/Install Kimi
Write-Host "📦 Checking Kimi CLI..." -ForegroundColor Blue
$kimi = Get-Command kimi -ErrorAction SilentlyContinue
if (-not $kimi) {
    Write-Host "Installing Kimi CLI..." -ForegroundColor Yellow
    pip install kimi-cli
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to install Kimi. Make sure Python and pip are installed." -ForegroundColor Red
        exit 1
    }
}
Write-Host "✅ Kimi is installed" -ForegroundColor Green

# Step 2: Check Kimi auth
Write-Host "`n🔐 Checking Kimi authentication..." -ForegroundColor Blue
$kimiInfo = kimi info 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Kimi is authenticated" -ForegroundColor Green
} else {
    Write-Host "⚠️  Please login to Kimi:" -ForegroundColor Yellow
    Write-Host "   kimi login" -ForegroundColor Gray
    exit 1
}

# Step 3: Find Pi
Write-Host "`n🔍 Searching for Raspberry Pi..." -ForegroundColor Blue

# Check ARP for Pi
$arpEntries = arp -a | Select-String "192\.168\."
$piIp = $null

# Common Pi subnets to check
$subnets = @("192.168.137", "192.168.2", "192.168.3", "10.0.0")

foreach ($subnet in $subnets) {
    $matches = $arpEntries | Select-String "$subnet\."
    if ($matches) {
        foreach ($match in $matches) {
            if ($match -match "\((\d+\.\d+\.\d+\.\d+)\)") {
                $ip = $matches[1]
                # Test SSH
                $test = Test-NetConnection -ComputerName $ip -Port 22 -WarningAction SilentlyContinue
                if ($test.TcpTestSucceeded) {
                    $piIp = $ip
                    Write-Host "✅ Found Pi at $ip (SSH open)" -ForegroundColor Green
                    break
                }
            }
        }
    }
    if ($piIp) { break }
}

if (-not $piIp) {
    Write-Host "⚠️  Could not automatically find Pi" -ForegroundColor Yellow
    $piIp = Read-Host "Enter Pi IP address manually (e.g., 192.168.137.10)"
}

# Step 4: Test Pi connection
Write-Host "`n🧪 Testing Pi connection..." -ForegroundColor Blue
$piReachable = Test-NetConnection -ComputerName $piIp -Port 22 -WarningAction SilentlyContinue
if (-not $piReachable.TcpTestSucceeded) {
    Write-Host "❌ Cannot reach Pi at $piIp port 22 (SSH)" -ForegroundColor Red
    Write-Host "   Make sure:" -ForegroundColor Yellow
    Write-Host "   1. Pi is connected via Ethernet" -ForegroundColor Yellow
    Write-Host "   2. SSH is enabled on Pi" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ Pi is reachable at $piIp" -ForegroundColor Green

# Step 5: Create directories
Write-Host "`n📁 Creating configuration..." -ForegroundColor Blue
$kimiDir = "$env:USERPROFILE\.kimi"
$masterDir = "$kimiDir\distributed\master"
$slaveDir = "$kimiDir\distributed\slave"

New-Item -ItemType Directory -Force -Path $masterDir | Out-Null
New-Item -ItemType Directory -Force -Path $slaveDir | Out-Null

# Step 6: Create nodes.json
$nodesConfig = @"
{
  "slaves": [
    {
      "node_id": "pi-ethernet-slave",
      "host": "$piIp",
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

$nodesConfig | Out-File -FilePath "$masterDir\nodes.json" -Encoding UTF8
Write-Host "✅ Created nodes.json with Pi IP: $piIp" -ForegroundColor Green

# Step 7: Create kimi-claw-distributed.toml
$kimiConfig = @"
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
You are Kimi-Claw, the unified AI agent with distributed computing.
You have a Raspberry Pi slave node at $piIp for offloading CPU tasks.
"""

[agent.distributed]
enabled = true
config_path = "~/.kimi/distributed/master/nodes.json"
auto_offload = true
local_load_threshold = 0.7
"@

$kimiConfig | Out-File -FilePath "$kimiDir\kimi-claw-distributed.toml" -Encoding UTF8
Write-Host "✅ Created Kimi config" -ForegroundColor Green

# Step 8: Create wrapper script
$wrapper = @'
@echo off
set CONFIG=%USERPROFILE%\.kimi\kimi-claw-distributed.toml

if "%1"=="--status" (
    echo Checking cluster status...
    kimi --config-file %CONFIG% --yes --prompt "List all connected slave nodes and their status"
    goto :eof
)

if "%1"=="--pi" (
    echo SSH to Pi...
    for /f "tokens=*" %%a in ('type %USERPROFILE%\.kimi\distributed\master\nodes.json ^| findstr "host"') do (
        for /f "tokens=2 delims=:\" %%b in ("%%a") do (
            ssh pi@%%b
            goto :eof
        )
    )
    goto :eof
)

if "%1"=="--help" (
    echo Kimi-Claw Commands:
    echo   --status    Check cluster status
    echo   --pi        SSH to Pi
    echo   "prompt"    Send prompt to Kimi
    goto :eof
)

kimi --config-file %CONFIG% %*
'@

$wrapper | Out-File -FilePath "$env:USERPROFILE\Desktop\kimi-claw.bat" -Encoding ASCII
Write-Host "✅ Created desktop shortcut: kimi-claw.bat" -ForegroundColor Green

# Step 9: Summary
Write-Host "`n===================================" -ForegroundColor Cyan
Write-Host "🎉 Setup Complete!" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor White
Write-Host "  Pi IP: $piIp" -ForegroundColor Gray
Write-Host "  Config: $kimiDir\kimi-claw-distributed.toml" -ForegroundColor Gray
Write-Host ""
Write-Host "Commands:" -ForegroundColor White
Write-Host "  kimi-claw --status     Check cluster" -ForegroundColor Gray
Write-Host "  kimi-claw --pi         SSH to Pi" -ForegroundColor Gray
Write-Host "  kimi-claw "hello"       Send message" -ForegroundColor Gray
Write-Host ""
Write-Host "Next: Install slave script on Pi" -ForegroundColor Yellow
Write-Host "  (Copy kimi_slave.py to Pi's ~/.kimi/distributed/slave/)" -ForegroundColor Gray
