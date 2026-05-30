# Windows TradingView Webhook Runbook

Last reviewed: 2026-05-06

This runbook covers the Windows-side TradingView webhook receiver in
`services/webhook/src/receiver.py`. The receiver listens on port `9090`, accepts
TradingView-style JSON payloads, optionally asks local Ollama for a short
quality verdict, and forwards a `TradeSignal`-shaped payload to the Mac signal
logger and legacy Pi API gateways over Tailscale.

This is a trading-adjacent ingress path. The receiver must remain paper-first,
locally scoped, and operator-reviewed before any internet exposure or live
execution dependency.

## Ownership

| Item | Path |
|---|---|
| Receiver | `services/webhook/src/receiver.py` |
| Windows env template | `services/webhook/.env.example` |
| Default port | `9090` |
| Health route | `/webhook/health` |
| Main route | `/webhook/tradingview` |
| Default log file | `C:/sapphire/webhook.log` |
| Primary forward target | `SIGNAL_LOGGER_MAC` -> `http://100.x.x.w:18081` |

## Current Safety Posture

Be precise about the current implementation:

- The receiver validates JSON shape, supported action, symbol normalization, and
  signal construction.
- If `WEBHOOK_SECRET` is configured, the receiver requires a matching
  `secret`, `webhook_secret`, `passphrase`, `X-Sapphire-Webhook-Secret`,
  `X-TradingView-Secret`, or `X-Webhook-Secret` value and compares it with a
  constant-time check. Bad secrets return HTTP 403.
- Invalid-payload logs redact secret-bearing fields and numeric fields must be
  finite. Oversized request bodies are rejected before JSON parsing.
- It sets `metadata.dry_run=true` when confidence is present and below `0.70`.
- It routes over Tailscale to local Sapphire services.
- It does not perform order placement itself.

Do not expose this receiver directly to the public internet without a reviewed
Cloudflare/Tailscale ingress path, secret rotation procedure, and downstream
paper-only gate verification.

## Normal Operation

On the Windows host, start manually for an attended session:

```powershell
cd C:\sapphire\webhook
python -m uvicorn src.receiver:app --host 0.0.0.0 --port 9090
```

From the commander Mac, check health over Tailscale:

```bash
curl -fsS http://100.x.x.z:9090/webhook/health | python3 -m json.tool
```

Check receiver status:

```bash
curl -fsS http://100.x.x.z:9090/status | python3 -m json.tool
```

Tail the Windows log on the Windows host:

```powershell
Get-Content C:\sapphire\webhook.log -Tail 100 -Wait
```

## Safe Test Payload

Use only paper/test routing. Do not send a real TradingView alert while
debugging.

```bash
curl -sS -X POST http://100.x.x.z:9090/webhook/tradingview \
  -H 'Content-Type: application/json' \
  -d '{
    "symbol":"BTCUSDT",
    "action":"buy",
    "price":65000,
    "confidence":0.50,
    "secret":"<WEBHOOK_SECRET>",
    "message":"operator dry-run test"
  }' | python3 -m json.tool
```

Expected behavior:

- HTTP 200 with `status: ok`.
- `metadata.dry_run` is true in the forwarded signal because confidence is
  below `0.70`.
- The receiver increments local stats.
- No order is placed by the receiver.

## Common Failures

### Health Route Fails

1. Confirm the Windows process is running.
2. Confirm Tailscale can reach the Windows host.
3. Confirm Windows firewall allows port `9090` on the Tailscale interface.
4. Check `C:/sapphire/webhook.log`.

### Payload Rejected With 400

The payload must include `symbol` and `action`, and `action` must be one of the
supported action strings in `VALID_ACTIONS`. Normalize TradingView alerts to
the shape accepted by `TradingViewAlert.from_webhook()`.

### Payload Rejected With 403

`WEBHOOK_SECRET` is configured and the payload/header did not match it. Do not
paste the secret into logs or PRs. Check the Windows environment and the
TradingView alert body/header template, then retry with a placeholder in any
shared notes.

### Signal Forwarding Fails

The receiver forwards to:

1. Mac signal logger `/api/signals`.
2. `rari2` API gateway `/api/signals/create`.
3. `rari1` API gateway `/api/signals/create`.

Failure of legacy Pi routes is not automatically an outage if the Mac logger
accepted the signal. Inspect the `publish.targets` array in the response and
the receiver log.

### Ollama Enrichment Times Out

Ollama enrichment is optional. Timeout or model failure should log a warning and
continue with `ai_verdict=null`. Do not block signal logging on enrichment.

## Known Follow-Ups

Before this receiver is considered production-ingress hardened:

1. Decide whether low-confidence `dry_run=true` should be a hard paper-only gate
   at the downstream consumer, not merely metadata.
2. Document the intended Cloudflare/Tailscale ingress path and rollback.
3. Add periodic replay/idempotency checks if TradingView alert retry behavior
   starts producing duplicate signals.

## Safety Notes

- Do not expose port `9090` publicly until auth enforcement lands.
- Do not put real secrets in curl examples, docs, issue comments, or PR bodies.
- Do not use the webhook to test live capital.
- Do not remove `dry_run` metadata without trading-critical-path review.
- Do not rely on Ollama output as execution authorization.

## Escalation

Escalate when:

- A real TradingView alert reached the receiver unexpectedly.
- An unauthorized source can reach port `9090`.
- The receiver forwarded a signal that downstream consumers treated as live
  execution.
- The Mac logger rejects a signal that the receiver accepted.

Include the payload shape without secrets, receiver response, target publish
results, and relevant signal-logger log lines.
