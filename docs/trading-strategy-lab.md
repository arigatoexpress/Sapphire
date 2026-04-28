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
- Hyperliquid order drafts model the exchange action shape but omit nonce and
  signature by design.
- Robinhood Chain integration targets testnet chain id `46630` only.
