# Cloudflare Tunnel Setup

Replaces all GCP Cloud Run public endpoints. Free tier supports unlimited tunnels.

## Why

TradingView can only POST webhooks to a public HTTPS URL. Previously this was GCP Cloud Run.
With the tunnel, the Windows PC (or any device) exposes a public endpoint without port-forwarding
or GCP.

## Quick tunnel (no Cloudflare account — temporary URL)

Use this for immediate verification. The URL changes on every restart, so it is **not suitable
for a persistent TradingView webhook**.

On the Windows PC (webhook host):

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:9090
```

Copy the printed `https://*.trycloudflare.com` URL and test:

```bash
curl https://<quick-url>/health
curl -X POST https://<quick-url>/webhook/tradingview \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","action":"buy","price":100000,"time":1234567890}'
```

## Named tunnel (persistent production URL)

### 1. Install on Windows PC (webhook host)

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login          # opens browser, authorize your domain
cloudflared tunnel create sapphire-tunnel
cloudflared tunnel list           # note the tunnel ID
```

### 2. DNS routing

In Cloudflare dashboard (or CLI):

```bash
cloudflared tunnel route dns sapphire-tunnel webhook.sapphirealpha.xyz
cloudflared tunnel route dns sapphire-tunnel dashboard.sapphirealpha.xyz
cloudflared tunnel route dns sapphire-tunnel pm.sapphirealpha.xyz
```

### 3. Configure

Copy `infra/cloudflare/tunnel-config.yml` to `C:\sapphire\tunnel-config.yml`, fill in:

- `<TUNNEL_ID>` (from `cloudflared tunnel list`)
- `<USERNAME>` (Windows username)
- `<DASHBOARD_TAILSCALE_IP:PORT>` (e.g. `100.x.x.x:8080`)
- `<PM_HUB_TAILSCALE_IP:PORT>` (e.g. `100.x.x.x:8082`)

### 4. Run as Windows service

```powershell
cloudflared service install --config C:\sapphire\tunnel-config.yml
```

## Endpoints exposed

| Public URL | Internal target | Host |
|-----------|----------------|------|
| webhook.sapphirealpha.xyz | localhost:9090 | Windows PC |
| dashboard.sapphirealpha.xyz | `<DASHBOARD_TAILSCALE_IP:PORT>` | Tailscale target |
| pm.sapphirealpha.xyz | `<PM_HUB_TAILSCALE_IP:PORT>` | Tailscale target |

## TradingView Pine Script update

After setup, update your Pine Script alerts to POST to:
`https://webhook.sapphirealpha.xyz/webhook/tradingview`
