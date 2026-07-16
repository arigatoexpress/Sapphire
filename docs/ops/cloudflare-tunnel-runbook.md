# Cloudflare Persistent Tunnel Runbook — Sapphire Webhook

**Scope:** Replace the temporary Cloudflare Quick Tunnel with a persistent named
tunnel so TradingView can POST alerts to `https://webhook.sapphirealpha.xyz`.

**Prerequisites:**
- Windows PC hosting the webhook receiver is online.
- `cloudflared` is installed at `C:\Program Files (x86)\cloudflared\cloudflared.exe`
  (helper script will install via winget if missing).
- You have access to the Cloudflare account that owns `sapphirealpha.xyz`.
- This runbook requires **interactive browser auth** — an agent cannot complete it.

---

## Step 1 — Open an Administrator PowerShell on the Windows PC

```powershell
# Run as Administrator
powershell.exe -ExecutionPolicy Bypass
```

---

## Step 2 — Run the helper script

```powershell
& "C:\sapphire\infra\cloudflare\setup-windows-tunnel.ps1"
```

The script will:
1. Install `cloudflared` via winget if it is missing.
2. Open your default browser to `https://dash.cloudflare.com/argotunnel` for
   `cloudflared tunnel login`.
3. Create the `sapphire-tunnel` named tunnel.
4. Route DNS:
   - `webhook.sapphirealpha.xyz`
   - `dashboard.sapphirealpha.xyz`
   - `pm.sapphirealpha.xyz`
5. Copy `C:\sapphire\infra\cloudflare\tunnel-config.yml` to `C:\sapphire\tunnel-config.yml`
   and fill in the tunnel ID and Windows username.
6. Install and start the `cloudflared` Windows service.

---

## Step 3 — Authenticate in the browser (interactive)

When the browser opens:
1. Log in to Cloudflare with the account that owns `sapphirealpha.xyz`.
2. Select the `sapphirealpha.xyz` zone/domain.
3. Approve the authentication request.
4. The page will show a success message and `cloudflared` will download a
   credentials file to:
   `C:\Users\<USERNAME>\.cloudflared\<TUNNEL_ID>.json`

**Do not close PowerShell until the script finishes.**

---

## Step 4 — Fill in the backend targets

After the script finishes, edit:

```powershell
notepad C:\sapphire\tunnel-config.yml
```

Replace these placeholders with real Tailscale destinations:

```yaml
- hostname: dashboard.sapphirealpha.xyz
  service: http://<DASHBOARD_TAILSCALE_IP:PORT>   # e.g. http://100.120.191.1:8080

- hostname: pm.sapphirealpha.xyz
  service: http://<PM_HUB_TAILSCALE_IP:PORT>      # e.g. http://100.120.191.1:8082
```

Save and close.

---

## Step 5 — Restart the tunnel service

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" service restart
```

Check the tunnel is listed and healthy:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel list
```

You should see `sapphire-tunnel` with an ID and a green status indicator.

---

## Step 6 — Verify the public endpoint

From any machine:

```bash
curl https://webhook.sapphirealpha.xyz/health
curl -X POST https://webhook.sapphirealpha.xyz/webhook/tradingview \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","action":"buy","price":100000,"time":1234567890,"secret":"YOUR_WEBHOOK_SECRET_HERE"}'
```

Expected:
- `/health` returns `{"status":"healthy",...}`.
- `/webhook/tradingview` returns `{"status":"ok",...}` for the first POST and
  `{"status":"duplicate",...}` for an identical second POST.

---

## Step 7 — Update TradingView alert URL

In your Pine Script alert configuration, set the webhook URL to:

```
https://webhook.sapphirealpha.xyz/webhook/tradingview
```

Ensure the alert body still includes `"secret": "YOUR_WEBHOOK_SECRET_HERE"` or
the value you configured in `C:\sapphire\webhook\.env`.

---

## Rollback

If the tunnel misbehaves, stop the service and fall back to a temporary Quick Tunnel:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" service stop
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:9090
```

Then update TradingView with the printed `*.trycloudflare.com` URL.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Browser auth fails | Make sure you select the `sapphirealpha.xyz` zone, not another domain. |
| `cloudflared tunnel list` is empty | Re-run `cloudflared tunnel login` and then `setup-windows-tunnel.ps1`. |
| DNS does not resolve | Check Cloudflare DNS dashboard for `webhook`, `dashboard`, `pm` CNAMEs. |
| Service fails to start | Verify `C:\sapphire\tunnel-config.yml` has the correct `<TUNNEL_ID>` and credentials path. |
| TradingView gets 403 | Update `WEBHOOK_SECRET` in `C:\sapphire\webhook\.env` and the Pine alert body to match. |

---

## Security notes

- The tunnel is ingress-only. The Windows PC initiates the outbound Cloudflare
  connection; no inbound firewall rules are required.
- TradingView alerts still cannot auto-place orders. Every signal is routed to
  the Telegram decision ledger for approval before execution.
- Rotate the webhook secret before going fully live.
