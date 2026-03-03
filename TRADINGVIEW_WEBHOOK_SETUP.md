# TradingView Webhook Setup Guide

## 🔗 Webhook Endpoint

```
https://sapphire-gateway-267358751314.us-central1.run.app/webhook/tradingview
```

## 🔐 Authentication Required

The webhook requires a secret for authentication. The Gateway accepts the secret from:

1. **Header:** `X-Sapphire-Webhook-Secret: your_secret`
2. **Body Fields:** `passphrase`, `secret`, or `token`

### Current Status
⚠️ The webhook secret is configured in GCP Secret Manager but needs to be verified or reset.

---

## 🛠️ Setup Options

### Option 1: Use GCP Secret Manager (Recommended)

Set the webhook secret in GCP Secret Manager:

```bash
# Generate a secure secret
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "Your webhook secret: $WEBHOOK_SECRET"

# Store in Secret Manager
gcloud secrets create sapphire-tradingview-webhook-secret \
  --data-file="-" \
  --project=sapphire-479610 \
  --location=us-central1 <<< "$WEBHOOK_SECRET"

# Or update existing secret
gcloud secrets versions add sapphire-tradingview-webhook-secret \
  --data-file="-" \
  --project=sapphire-479610 \
  --location=us-central1 <<< "$WEBHOOK_SECRET"
```

Then redeploy the Gateway to pick up the new secret:

```bash
gcloud run deploy sapphire-gateway \
  --image gcr.io/sapphire-479610/sapphire-gateway:latest \
  --region=us-central1 \
  --project=sapphire-479610
```

---

### Option 2: Modify Gateway to Accept Query Parameter

For easier TradingView integration, you can modify the Gateway to accept the secret as a query parameter:

**File:** `services/api-gateway/src/main.py`

Add this to the `_validate_tradingview_secret` function:

```python
def _validate_tradingview_secret(
    payload: Dict[str, Any], 
    header_secret: Optional[str],
    query_secret: Optional[str] = None  # Add this parameter
) -> None:
    if not TRADINGVIEW_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="TradingView webhook secret is not configured",
        )

    body_secret = _extract_text(payload, ["passphrase", "secret", "token"])
    if (
        (header_secret and header_secret == TRADINGVIEW_WEBHOOK_SECRET)
        or (body_secret and body_secret == TRADINGVIEW_WEBHOOK_SECRET)
        or (query_secret and query_secret == TRADINGVIEW_WEBHOOK_SECRET)  # Add this check
    ):
        return
    state.tradingview_ingress_stats["rejected"] += 1
    raise HTTPException(status_code=401, detail="Invalid webhook secret")
```

Then in the webhook handler:

```python
query_secret = request.query_params.get("secret")
_validate_tradingview_secret(payload, x_sapphire_webhook_secret, query_secret)
```

---

## 📋 TradingView Alert Configuration

### Step 1: Pine Script Strategy

Add alert conditions to your strategy:

```pinescript
//@version=5
strategy("Sapphire Alpha", overlay=true)

// Your strategy logic here
fastEMA = ta.ema(close, 9)
slowEMA = ta.ema(close, 21)

longCondition = ta.crossover(fastEMA, slowEMA)
shortCondition = ta.crossunder(fastEMA, slowEMA)

if (longCondition)
    strategy.entry("Long", strategy.long)
    
if (shortCondition)
    strategy.close("Long")
    strategy.entry("Short", strategy.short)

// Plot for webhook
plot(fastEMA, "Fast EMA", color.blue)
plot(slowEMA, "Slow EMA", color.orange)
```

### Step 2: Create Alert

1. Click the "Alerts" icon (clock) in TradingView
2. Click "Create Alert"
3. Set **Condition:** `Sapphire Alpha` - order fill events
4. Set **Frequency:** Once per bar close (recommended)

### Step 3: Webhook Settings

**Webhook URL:**
```
https://sapphire-gateway-267358751314.us-central1.run.app/webhook/tradingview
```

**Message (JSON):**
```json
{
  "symbol": "{{ticker}}",
  "price": {{close}},
  "side": "{{strategy.order.action}}",
  "action": "{{strategy.order.action}}",
  "timestamp": "{{time}}",
  "interval": "{{interval}}",
  "strategy": "sapphire_alpha_v1",
  "passphrase": "YOUR_WEBHOOK_SECRET_HERE",
  "metadata": {
    "volume": {{volume}},
    "position_size": {{strategy.position_size}},
    "commission": {{strategy.commission}},
    "fast_ema": {{plot_0}},
    "slow_ema": {{plot_1}}
  }
}
```

### Step 4: Alert Name Template
```
Sapphire: {{ticker}} {{strategy.order.action}} @ {{close}}
```

---

## 🧪 Testing the Webhook

Once the secret is configured, test with curl:

```bash
curl -X POST "https://sapphire-gateway-267358751314.us-central1.run.app/webhook/tradingview" \
  -H "Content-Type: application/json" \
  -H "X-Sapphire-Webhook-Secret: YOUR_SECRET_HERE" \
  -d '{
    "symbol": "BTCUSDT",
    "price": 69010.50,
    "side": "buy",
    "action": "open_long",
    "timestamp": "2026-03-03T01:00:00Z",
    "interval": "1h",
    "strategy": "test"
  }'
```

Expected response:
```json
{
  "status": "published",
  "message_id": "...",
  "signal_id": "...",
  "symbol": "BTCUSDT",
  "action": "open_long"
}
```

---

## 📊 Supported Actions

| Action | Description |
|--------|-------------|
| `open_long` | Open long position |
| `close_long` | Close long position |
| `open_short` | Open short position |
| `close_short` | Close short position |
| `cancel_all` | Cancel all pending orders |

---

## 🔍 Monitoring

Check webhook status:
```bash
curl https://sapphire-gateway-267358751314.us-central1.run.app/webhook/health
```

View recent signals in the dashboard:
- https://sapphirealpha.xyz/intelligence

---

## ⚠️ Security Notes

1. **Keep your webhook secret secure** - Never commit it to git
2. **Use HTTPS only** - TradingView supports HTTPS webhooks
3. **Idempotency protection** - Duplicate signals within 5 minutes are ignored
4. **IP not verified** - TradingView uses dynamic IPs, so IP filtering isn't possible

---

## 🆘 Troubleshooting

### "Invalid webhook secret"
- Verify the secret matches what's in Secret Manager
- Check that you're using the correct header name: `X-Sapphire-Webhook-Secret`
- Or include in body as: `passphrase`, `secret`, or `token`

### "TradingView webhook secret is not configured"
- The `SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET` env var is empty
- Set it in GCP Secret Manager and redeploy Gateway

### "Missing symbol"
- Your JSON must include a `symbol` field
- Use TradingView's `{{ticker}}` variable

### "Unsupported action"
- Use one of the supported actions listed above
- Check for typos in the action field

---

## 🔗 Related Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /webhook/health` | Check webhook status |
| `POST /webhook/tradingview` | Receive TradingView signals |
| `GET /api/trading/signals` | View recent signals |
| `GET /api/trading/metrics` | View trading metrics |

---

**Last Updated:** 2026-03-03  
**Gateway Version:** v2.0  
**Status:** Pending webhook secret configuration
