# GCP → On-Prem Migration Runbook

Migrating all Sapphire OS services from GCP Cloud Run / Firestore / Pub/Sub
to on-prem hardware (rari1, rari2, Windows PC) over Tailscale.

## Architecture After Migration

```
[TradingView]
    │ HTTPS alert
    ▼
[Cloudflare Tunnel] → webhook.sapphirealpha.xyz
    │
    ▼
[Windows PC :9090] sapphire-webhook
    │ Ollama enrichment (gemma3:27b)
    │ POST over Tailscale
    ├──▶ [rari1 :18081] sapphire-alpha-engine
    └──▶ [rari2 :18081] sapphire-alpha-engine
              │ Redis pub/sub (rari1:6379)
              ├──▶ [rari2] aster-bot
              └──▶ [rari2] hyperliquid-bot
              │
              ▼
         [rari1 :8082] control-plane (PM hub)
              │
              ▼
         [Telegram] → @RariSapphireBot
```

## Status

| Component | Status | Notes |
|-----------|--------|-------|
| Redis (rari1) | ✅ Live | rari1:6379, accessible from rari2 |
| control-plane | ✅ Live | rari1:8082 — PM bridge operational |
| webhook (Windows PC) | ⬜ Start | `uvicorn src.receiver:app --port 9090` |
| Cloudflare Tunnel | ⬜ Setup | See `infra/cloudflare/SETUP.md` |
| alpha-engine rari1 | ✅ Running | port 18081 |
| alpha-engine rari2 | ✅ Running | port 18081 |
| api-gateway rari1 | ✅ Running | port 18080 — signals endpoint live |
| api-gateway rari2 | ✅ Running | port 18080 |
| dashboard rari1 | ✅ Running | port 8080 |
| kimi-claw rari1 | ✅ Running | Telegram bot, pointed to local gateway |
| kimi-claw-slave rari2 | ✅ Running | orchestrator, pointed to local gateway |
| GCP project | ⬜ Delete | After webhook + Cloudflare confirmed |

## Step-by-Step

### 1. Install Redis on rari1

```bash
ssh rari@100.x.x.x 'bash -s' < infra/pi/rari1/setup-redis.sh
```

### 2. Update service .env files on rari1 + rari2

Add to each service's `.env`:
```
REDIS_URL=redis://100.x.x.x:6379
```

Reference: `infra/pi/rari1/env.example`, `infra/pi/rari2/env.example`

### 3. Restart aster + hyperliquid on rari2

```bash
ssh rari@100.x.x.y
sudo systemctl restart sapphire-aster sapphire-hyperliquid
sudo systemctl status sapphire-aster sapphire-hyperliquid
```

### 4. Deploy control-plane on rari1

```bash
bash infra/pi/rari1/deploy-control-plane.sh
```

Fill in `/mnt/ssd/sapphire/control-plane/.env` based on `.env.example`.

### 5. Start webhook on Windows PC

```powershell
cd C:\sapphire\webhook
cp .env.example .env   # fill in WEBHOOK_SECRET
pip install -r requirements.txt
python -m uvicorn src.receiver:app --host 0.0.0.0 --port 9090
```

### 6. Set up Cloudflare Tunnel (Windows PC)

Follow `infra/cloudflare/SETUP.md`.
Update TradingView alerts to: `https://webhook.sapphirealpha.xyz/webhook/tradingview`

### 7. Verify signal flow

```bash
# Test from Mac:
curl -X POST http://100.x.x.z:9090/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"symbol":"ETHUSD","action":"buy","price":3500,"secret":"sapphire_trading_2024"}'
```

### 8. Delete GCP project

Once all services confirmed healthy for 48h:
```bash
gcloud projects delete sapphire-479610
```

Or suspend billing: https://console.cloud.google.com/billing

## GCP Dependencies Removed

| Service | Was | Now |
|---------|-----|-----|
| Signal bus | GCP Pub/Sub | Redis Streams (rari1:6379) |
| Chat state | Firestore | In-memory (control-plane) |
| Task state | Firestore | SQLite (rari1 SSD) |
| Runtime policy | Firestore | Local JSON file |
| Events | Firestore | JSONL file (rari1 SSD) |
| Webhook | Cloud Run | Windows PC + Cloudflare Tunnel |
| Alpha engine | Cloud Run | rari1 + rari2 (already running) |
| Dashboard | Cloud Run | rari1:8080 (already running) |
| Control plane | Cloud Run | rari1:8082 (new) |
| Secrets | Secret Manager | Local .env files |
