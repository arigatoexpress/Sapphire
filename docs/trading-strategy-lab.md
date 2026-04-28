# Sapphire Trading Strategy Lab

The strategy lab is a dry-run surface for testing TradingView-driven strategy
ideas across Sapphire's paper stack, Robinhood Crypto read paths, Hyperliquid
market data/order drafts, and Robinhood Chain testnet attestations.

## Safety Floor

- Live trading remains disabled. The lab returns drafts only; it never signs,
  submits, cancels, or replaces exchange orders.
- Keep `TRADINGVIEW_EXECUTION_ENABLED=false` until paper validation has enough
  passing evidence and Ari explicitly approves a live toggle.
- Do not put credentials, private keys, session cookies, or account identifiers
  in TradingView webhook bodies.
- Telegram testing stays in dry-run formatting paths only.

## Dashboard APIs

- `GET /api/analytics/market-universe` returns Sapphire-liked tokens, current
  CoinGecko trending tokens, corrected aliases, and venue symbol mappings.
- `GET /api/tradingview/capabilities` returns the full TradingView capability
  matrix: webhook alerts, Pine strategy fills, Advanced Charts datafeed needs,
  Trading Platform Broker API endpoints, and local CDP observability.
- `GET /api/trading/strategy-lab` returns the combined strategy lab report.
- `GET /api/trading/shadow-controller` returns a risk-managed paper-shadow
  trading report: ranked candidates, capped manual-order dry-run instructions,
  blocked live surfaces, and promotion gates. Add `?offline=1` to skip public
  market-data fetches.
- `POST /api/trading/order-draft` returns venue payload drafts for a symbol,
  action, and notional without signing or submitting anything.
- The strategy-lab report includes `real_funds_readiness`, which documents the
  Robinhood Crypto pilot caps and why stock automation remains blocked.

Example draft request:

```bash
curl -s -X POST http://127.0.0.1:5000/api/trading/order-draft \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","action":"buy","notional_usd":100,"strategy":"sma_lab"}'
```

## Symbol Corrections

The lab canonicalizes venue symbols before routing:

- `HYPER`, `HYPERUSDT`, and `HYPEUSDT` -> `HYPE`
- `MATIC`, `MATICUSDT`, and `MATICUSD` -> `POL`
- `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, and similar USD/USDT forms -> base symbols

## Source Notes

- TradingView webhooks send an HTTP POST to the configured URL; valid JSON
  bodies are sent as `application/json`.
- TradingView strategy placeholders such as `{{ticker}}`,
  `{{strategy.order.action}}`, `{{strategy.order.contracts}}`, and
  `{{strategy.market_position}}` are represented in the lab alert template.
- Robinhood Crypto API support is kept read-first in Sapphire; order payloads
  here are v2-shaped intent drafts only.
- `scripts/ops/robinhood_live_readiness.py` renders an offline readiness report
  without network calls, secret reads, signatures, or order submission.
- `scripts/ops/robinhood_live_readiness.py --live-read-only` may load local
  Robinhood credentials and call read-only API endpoints, but still redacts
  account identifiers and cannot submit orders.
- `scripts/ops/robinhood_manual_order.py` is the only manual live-order utility;
  it defaults to dry-run, enforces the pilot cap, requires a typed confirmation
  token for `--execute`, and is not wired into dashboard, scheduler, Telegram, or
  TradingView paths.
- `scripts/ops/trading_shadow_controller.py` automates candidate ranking and
  paper-shadow reporting only. Its generated manual-order command omits
  `--execute` and uses a placeholder limit price until the live-read-only
  readiness probe supplies a just-in-time guarded price.
- Hyperliquid order drafts model the exchange action shape but omit nonce and
  signature by design.
- Robinhood Chain integration targets testnet chain id `46630` only.

## Shadow Controller

The shadow controller is the highest-autonomy trading component currently
allowed in Sapphire. It can run unattended for market screening, but it cannot
spend money.

What it automates:

- Score Sapphire-liked crypto assets using priority, tags, public market data,
  Robinhood Crypto tradability, and 24-hour change bands.
- Cap every candidate at the existing `$5` first-order pilot limit.
- Generate paper order drafts for all candidate venues.
- Emit a manual Robinhood dry-run command for review without `--execute`.
- Write an optional JSON report for dashboard or operator review:

  ```bash
  python3 scripts/ops/trading_shadow_controller.py --output
  ```
- Run every 30 minutes via the versioned paper-only LaunchAgent
  `infra/launchagents/com.sapphire.trading-shadow-controller.plist` once that
  plist is installed.

What remains blocked:

- Scheduler, dashboard, Telegram, and TradingView live-submit paths.
- Any Robinhood stock, ETF, or options automation through unofficial endpoints.
- Any future live order that lacks Ari's exact one-order confirmation token.
