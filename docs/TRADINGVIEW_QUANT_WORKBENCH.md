# TradingView Quant Workbench Integration (Sapphire)

## Objective
Use your TradingView account as a strategy research and signal-generation workbench, then route validated alerts into Sapphire control plane.

## Reality Constraints (Official)

- TradingView does not offer a general public API for direct platform data extraction for bots.
- Production integration should use TradingView Alerts + Webhooks.
- TradingView itself warns alerts/webhooks are not a complete unattended execution stack without safeguards.

Reference docs:

- TradingView support, API limitations: <https://www.tradingview.com/support/solutions/43000474416-i-want-to-get-data-from-tradingview-on-my-own-site-application/>
- TradingView webhook alerts: <https://www.tradingview.com/support/solutions/43000529348-about-webhooks/>
- TradingView alert behavior and retries: <https://www.tradingview.com/support/solutions/43000735201-why-might-i-have-not-received-an-alert-notification-on-the-webhook-url-or-alert-sound/>

## Target Architecture

1. Build or clone public indicators/strategies in TradingView Pine.
2. Use alert payloads (JSON) with explicit action, symbol, quantity, venue.
3. Send alerts to `POST /tradingview/webhook` on `sapphire-alpha`.
4. `sapphire-alpha` validates secret and maps signals to:
   - heartbeat/control commands, or
   - venue trade intents (`ASTER`, `LIGHTER`).
5. Start in dry-run mode (`TRADINGVIEW_EXECUTION_ENABLED=false`), then enable live execution only after validation.

## Alert Payload Standards

### 1) Heartbeat

```json
{
  "action": "heartbeat",
  "source": "tradingview",
  "strategy": "tv-health-check",
  "secret": "${TRADINGVIEW_WEBHOOK_SECRET}"
}
```

### 2) Status Request

```json
{
  "action": "status",
  "source": "tradingview",
  "strategy": "tv-status",
  "secret": "${TRADINGVIEW_WEBHOOK_SECRET}"
}
```

### 3) Trade Intent (Dry-run then Live)

```json
{
  "action": "buy",
  "venue": "ASTER",
  "symbol": "SOL",
  "quantity": 0.25,
  "strategy": "tv-breakout-v1",
  "timeframe": "15m",
  "secret": "${TRADINGVIEW_WEBHOOK_SECRET}"
}
```

## Promotion Workflow

1. Research strategy in TradingView with realistic fees/slippage assumptions.
2. Paper-run alerts into Sapphire for at least 7 days.
3. Compare alert-to-fill quality and false-positive rate.
4. Enable live mode only for one venue and one symbol bucket.
5. Expand capital only after stable positive expectancy.

## Risk Controls Required Before Live

- Kill switch tested (`/kill` and `/resume`).
- Per-venue allocation limits configured.
- Max daily loss and consecutive-loss halts active.
- Secret rotation policy for webhook and Telegram controls.
- Idempotency guard active (`TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS`).
- Per-venue max quantity caps configured (`TRADINGVIEW_MAX_QUANTITY_*`).
- Symbol allowlists configured for each venue (`TRADINGVIEW_ALLOWED_SYMBOLS_*`).

## Operational Checklist

- Secret exists in GCP: `TRADINGVIEW_WEBHOOK_SECRET`.
- Alpha env has `TRADINGVIEW_EXECUTION_ENABLED=false` during validation.
- Telegram receives every accepted TradingView signal.
- Scheduler heartbeat remains active for independent liveness checks.
- Duplicate alerts are ignored (same signal in idempotency window).
- Oversized quantities are capped before dispatch.

## Next Build Items

1. Add strategy-specific allowlists for symbols and max order size.
2. Add idempotency keys for duplicate alert protection.
3. Add per-strategy PnL attribution and automatic demotion rules.
