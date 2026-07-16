#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Set up a persistent Cloudflare Tunnel on the Windows webhook host.

.DESCRIPTION
  Installs cloudflared (if missing), creates a named tunnel, routes DNS for
  webhook.sapphirealpha.xyz/dashboard/pm, copies the config template, and
  installs the Windows service. The browser auth step (`cloudflared tunnel login`)
  requires interactive user approval.

  Run this script on the Windows PC that hosts services/webhook/src/receiver.py.
#>

$ErrorActionPreference = "Stop"

$CloudflaredPath = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$SapphireDir = "C:\sapphire"
$ConfigSource = "\Users\aribs\Code\Sapphire\infra\cloudflare\tunnel-config.yml"
$ConfigDest = "$SapphireDir\tunnel-config.yml"

function Test-Cloudflared {
    if (Test-Path $CloudflaredPath) { return }
    Write-Host "Installing cloudflared via winget..."
    winget install Cloudflare.cloudflared
    if (-not (Test-Path $CloudflaredPath)) {
        throw "cloudflared installation failed"
    }
}

Test-Cloudflared

# Auth step requires browser interaction.
Write-Host "Opening browser for Cloudflare authentication..."
& $CloudflaredPath tunnel login
if ($LASTEXITCODE -ne 0) { throw "cloudflared tunnel login failed" }

Write-Host "Creating sapphire-tunnel..."
& $CloudflaredPath tunnel create sapphire-tunnel
if ($LASTEXITCODE -ne 0) { throw "cloudflared tunnel create failed" }

$Tunnels = & $CloudflaredPath tunnel list --format=json | ConvertFrom-Json
$Tun = $Tunnels | Where-Object { $_.name -eq "sapphire-tunnel" } | Select-Object -First 1
if (-not $Tun) { throw "sapphire-tunnel not found after creation" }
$TunId = $Tun.id
$Username = $env:USERNAME
$CredFile = "C:\Users\$Username\.cloudflared\$TunId.json"

Write-Host "Routing DNS..."
& $CloudflaredPath tunnel route dns sapphire-tunnel webhook.sapphirealpha.xyz
& $CloudflaredPath tunnel route dns sapphire-tunnel dashboard.sapphirealpha.xyz
& $CloudflaredPath tunnel route dns sapphire-tunnel pm.sapphirealpha.xyz

New-Item -ItemType Directory -Force -Path $SapphireDir | Out-Null
Write-Host "Copying config template..."
Copy-Item -Path $ConfigSource -Destination $ConfigDest -Force

# Fill in placeholders.
$Config = Get-Content $ConfigDest -Raw
$Config = $Config -replace "<TUNNEL_ID>", $TunId
$Config = $Config -replace "<USERNAME>", $Username
$Config = $Config -replace "<DASHBOARD_TAILSCALE_IP:PORT>", "DASHBOARD_TAILSCALE_IP:PORT"
$Config = $Config -replace "<PM_HUB_TAILSCALE_IP:PORT>", "PM_HUB_TAILSCALE_IP:PORT"
Set-Content -Path $ConfigDest -Value $Config -NoNewline

Write-Host "Installing Windows service..."
& $CloudflaredPath service install --config $ConfigDest
& $CloudflaredPath service start

Write-Host "Done. Config: $ConfigDest"
Write-Host "Edit the config to set DASHBOARD_TAILSCALE_IP:PORT and PM_HUB_TAILSCALE_IP:PORT, then restart the service."
