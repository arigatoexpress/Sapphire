# TradingView Quant Workbench Integration (Sapphire)

Status (2026-02-16):

- TradingView webhook ingress is currently disabled in production.
- `/tradingview/webhook` on `sapphire-alpha` is not deployed (HTTP `404`).
- Scheduler jobs that target `/tradingview/webhook` are paused by default.

This document is retained as a design spec for re-enabling TradingView as a workbench later.

## Objective
Use your TradingView account as a strategy research/backtest workbench, while live execution and analysis stay DEX-native on ASTER/LIGHTER.

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
   - venue trade intents (`ASTER`, `LIGHTER`) only when live signal mode is explicitly enabled.
5. Workspace actions are sent through the TradingView autonomy plugin and dispatched to OpenClaw gateway hooks for browser-level execution.
6. Keep default workbench mode (`TRADINGVIEW_EXECUTION_ENABLED=false`) and enable live signal execution only for controlled windows.

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
  "strategy": "tv-aster-breakout",
  "timeframe": "15m",
  "secret": "${TRADINGVIEW_WEBHOOK_SECRET}"
}
```

When `TRADINGVIEW_ENFORCE_STRATEGY_RULES=true`, `strategy` is required and must match
`TRADINGVIEW_STRATEGY_RULES_JSON`.

### 4) Workspace Mutation (Watchlist + Community Script)

```json
{
  "action": "tv_watchlist_add",
  "watchlist": "SAPPHIRE",
  "symbol": "ETH",
  "strategy": "tv-lighter-momentum",
  "secret": "${TRADINGVIEW_WEBHOOK_SECRET}"
}
```

```json
{
  "action": "tv_script_add",
  "script": "LuxAlgo - Signals & Overlays",
  "secret": "${TRADINGVIEW_WEBHOOK_SECRET}"
}
```

### 5) TA Request

```json
{
  "action": "tv_ta",
  "symbol": "SOL",
  "venue": "ASTER",
  "closes": [149.5,149.8,150.2,151.1,150.7,151.4,152.0],
  "secret": "${TRADINGVIEW_WEBHOOK_SECRET}"
}
```

### 6) Backtest Request

```json
{
  "action": "tv_backtest",
  "strategy": "tv-aster-breakout",
  "symbol": "SOL",
  "timeframe": "15",
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
- Strategy rules configured and enforced (`TRADINGVIEW_ENFORCE_STRATEGY_RULES=true`).
- TradingView autonomy plugin enabled (`TRADINGVIEW_AUTONOMY_ENABLED=true`).
- OpenClaw hook dispatch configured (`TRADINGVIEW_AUTONOMY_HOOK_URL` + token).
- Full asset scope + community script access explicitly enabled.

## Operational Checklist

- Secret exists in GCP: `TRADINGVIEW_WEBHOOK_SECRET`.
- Alpha env has `TRADINGVIEW_EXECUTION_ENABLED=false` during validation.
- Alpha env has venue allowlists configured:
  - `TRADINGVIEW_ALLOWED_SYMBOLS_ASTER=SOL;JUP;PYTH;BONK;WIF`
  - `TRADINGVIEW_ALLOWED_SYMBOLS_LIGHTER=BTC;ETH;SOL;HYPE;DOGE;AVAX`
- Alpha env enforces strategy rules:
  - `TRADINGVIEW_ENFORCE_STRATEGY_RULES=true`
  - `TRADINGVIEW_STRATEGY_RULES_JSON` maps strategy name to allowed venues/symbols/size caps
- Alpha env enables workspace autonomy:
  - `TRADINGVIEW_AUTONOMY_ENABLED=true`
  - `TRADINGVIEW_ALLOW_ALL_ASSETS=true`
  - `TRADINGVIEW_COMMUNITY_ACCESS_ENABLED=true`
  - `TRADINGVIEW_AUTONOMY_HOOK_TOKEN` loaded from `OPENCLAW_GATEWAY_TOKEN`
- Telegram receives every accepted TradingView signal.
- Scheduler heartbeat remains active for independent liveness checks.
- Duplicate alerts are ignored (same signal in idempotency window).
- Oversized quantities are capped before dispatch.

## Next Build Items

1. Add strategy-specific allowlists for symbols and max order size.
2. Add idempotency keys for duplicate alert protection.
3. Add per-strategy PnL attribution and automatic demotion rules.
