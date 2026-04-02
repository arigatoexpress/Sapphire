---
name: sapphire-webhook
description: TradingView webhook receiver — validates and routes signals to alpha engine
type: service
runtime: python
deploy_target: windows-pc
dependencies: [sapphire-core]
entry_point: src/receiver.py
test_command: pytest tests/
---

# services/webhook

Lightweight FastAPI service that receives TradingView alerts and routes them to the alpha engine. Validates webhook secrets, normalizes signal format, and publishes a `type:trading` event.

## Signal Schema

```json
{
  "symbol": "ETHUSD",
  "action": "buy" | "sell" | "close",
  "strategy": "v3_ultra" | "multi_screener",
  "price": 3200.50,
  "confidence": 0.87
}
```

## Security

- Webhook secret validated in payload body (`secret` field must match `WEBHOOK_SECRET` env var)
- No GCP Secret Manager — secret set in local `.env` on Windows PC

## Deploy (on-prem — Windows PC)

Signal routing: TradingView → Cloudflare Tunnel → Windows PC:9090 → rari1:18081 + rari2:18081 (Tailscale)

```powershell
# Set env vars in C:\sapphire\.env
# WEBHOOK_SECRET, ALPHA_ENGINE_RARI1, ALPHA_ENGINE_RARI2, OLLAMA_URL

cd C:\sapphire\webhook
python -m uvicorn src.receiver:app --host 0.0.0.0 --port 9090

# TradingView alert URL: https://webhook.sapphirealpha.xyz/webhook/tradingview
```

## Cloudflare Tunnel

See `infra/cloudflare/SETUP.md` for public HTTPS ingress setup.
