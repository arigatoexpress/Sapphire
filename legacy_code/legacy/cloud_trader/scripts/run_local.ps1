# run_local.ps1
# Local development script for Sapphire V2 on Windows
# Usage: .\scripts\run_local.ps1

param(
    [switch]$SkipDocker,
    [switch]$Debug,
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

Write-Host "=== Sapphire V2 Local Development ===" -ForegroundColor Cyan
Write-Host "Project Directory: $ProjectDir"

# Change to project directory
Set-Location $ProjectDir

# Check for .env.local
if (-not (Test-Path ".env.local")) {
    Write-Host "WARNING: .env.local not found. Creating from template..." -ForegroundColor Yellow
    if (Test-Path ".env.local.template") {
        Copy-Item ".env.local.template" ".env.local"
        Write-Host "Created .env.local from template. Please edit it with your API keys." -ForegroundColor Yellow
        Write-Host "Then run this script again." -ForegroundColor Yellow
        exit 1
    } else {
        Write-Host "ERROR: .env.local.template not found!" -ForegroundColor Red
        exit 1
    }
}

# Start infrastructure if not skipped
if (-not $SkipDocker) {
    Write-Host "`nStarting local infrastructure (Redis, PubSub)..." -ForegroundColor Green

    # Check if Docker is running
    try {
        docker info > $null 2>&1
    } catch {
        Write-Host "ERROR: Docker is not running. Please start Docker Desktop." -ForegroundColor Red
        exit 1
    }

    # Start docker-compose
    docker-compose -f docker-compose.local.yml up -d

    # Wait for services to be ready
    Write-Host "Waiting for services to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3

    # Check Redis
    try {
        $redis = docker exec sapphire-redis redis-cli ping 2>$null
        if ($redis -eq "PONG") {
            Write-Host "  Redis: OK" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Redis: Starting..." -ForegroundColor Yellow
    }
}

# Load environment variables from .env.local
Write-Host "`nLoading environment from .env.local..." -ForegroundColor Green
Get-Content ".env.local" | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

# Set local overrides
[Environment]::SetEnvironmentVariable("REDIS_HOST", "localhost", 'Process')
[Environment]::SetEnvironmentVariable("REDIS_PORT", "6379", 'Process')
[Environment]::SetEnvironmentVariable("PUBSUB_EMULATOR_HOST", "localhost:8085", 'Process')

# Run the application
Write-Host "`nStarting Sapphire V2 on port $Port..." -ForegroundColor Green
Write-Host "Health check: http://localhost:$Port/health" -ForegroundColor Cyan
Write-Host "API docs: http://localhost:$Port/docs" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Yellow

if ($Debug) {
    # Debug mode with more verbose output
    $env:LOG_LEVEL = "DEBUG"
    python -m uvicorn cloud_trader.api:app --reload --port $Port --log-level debug
} else {
    python -m uvicorn cloud_trader.api:app --reload --port $Port
}
