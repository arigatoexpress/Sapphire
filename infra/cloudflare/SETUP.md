# Cloudflare Tunnel Setup

Replaces all GCP Cloud Run public endpoints. Free tier supports unlimited tunnels.

## Why

TradingView can only POST webhooks to a public HTTPS URL. Previously this was GCP Cloud Run.
With the tunnel, the Windows PC (or any device) exposes a public endpoint without port-forwarding
or GCP.

## Install (Windows PC — webhook host)

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login          # opens browser, authorize your domain
cloudflared tunnel create sapphire-tunnel
cloudflared tunnel list           # note the tunnel ID
```

## DNS routing

In Cloudflare dashboard (or CLI):
```bash
cloudflared tunnel route dns sapphire-tunnel webhook.sapphirealpha.xyz
cloudflared tunnel route dns sapphire-tunnel dashboard.sapphirealpha.xyz
cloudflared tunnel route dns sapphire-tunnel pm.sapphirealpha.xyz
```

## Configure

Copy `tunnel-config.yml`, fill in your tunnel ID and credentials path.

## Run as Windows service

```powershell
cloudflared service install --config C:\sapphire\tunnel-config.yml
```

## Endpoints exposed

| Public URL | Internal target | Host |
|-----------|----------------|------|
| webhook.sapphirealpha.xyz | localhost:9090 | Windows PC |
| dashboard.sapphirealpha.xyz | 100.120.191.1:8080 | rari1 (via Tailscale) |
| pm.sapphirealpha.xyz | 100.120.191.1:8082 | rari1 (via Tailscale) |

## TradingView Pine Script update

After setup, update your Pine Script alerts to POST to:
`https://webhook.sapphirealpha.xyz/webhook/tradingview`
