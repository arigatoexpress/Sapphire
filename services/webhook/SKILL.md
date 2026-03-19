---
name: sapphire-webhook
description: TradingView webhook receiver — validates and routes signals to alpha engine
type: service
runtime: python
deploy_target: cloud-run
dependencies: [sapphire-core]
entry_point: src/main.py
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

- Webhook secret validated via `X-Webhook-Secret` header
- Secret stored in: `sapphire-webhook-secret` (Secret Manager)
- Only accepts POST /webhook — all other routes 404

## Deploy

```bash
gcloud run deploy sapphire-webhook --source . --project sapphire-479610
# TradingView alert URL: https://webhook.sapphirealpha.xyz/webhook
```
