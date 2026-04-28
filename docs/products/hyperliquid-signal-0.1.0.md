# Hyperliquid Public-Feed Signals 0.1.0

## Purpose

Sapphire subscribes to Hyperliquid public WebSocket feeds and emits
microstructure signals into the event bus. This product is signal-only and
paper-only: it does not read wallet keys, call authenticated endpoints, or place
orders.

Official feed contracts used here:

- WebSocket mainnet endpoint: `wss://api.hyperliquid.xyz/ws`
- Public subscriptions: `trades`, `bbo`, and `l2Book`
- Data shapes: `WsTrade[]`, `WsBbo`, and `WsBook`

References:

- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions

## Inputs

Default symbols are `BTC`, `ETH`, and `SOL`.

Operators can override symbols with:

```yaml
symbols:
  - BTC
  - ETH
  - SOL
```

Config path: `~/.sapphire/hyperliquid_symbols.yaml`

The feed enforces `MAX_SYMBOLS=8`; extra configured symbols are ignored.

## Signals

| Topic | Rule | Payload intent |
| --- | --- | --- |
| `hyperliquid.trade` | Trade notional exceeds `$250,000` | Large public tape print |
| `hyperliquid.imbalance` | Top-of-book bid/ask notional imbalance exceeds `3:1` for more than `10s` | Sustained microstructure pressure |
| `hyperliquid.book.thin` | Top-10 bid+ask depth drops more than `30%` inside `60s` | Sudden liquidity thinning |

All emitted payloads include:

- `schema_version=hyperliquid.signal.v1`
- `source=hyperliquid-public-feed`
- `paper_only=true`
- `live_trading_enabled=false`

## Safety Caps

| Cap | Value |
| --- | ---: |
| Max symbols | `8` |
| Max signals per hour | `240` |
| Max reconnect attempts per hour | `12` |

The daemon is blocked unless `SAPPHIRE_HYPERLIQUID_LIVE=1`. That flag enables
only public WebSocket reads. It does not enable trading.

## Operator Tool

```bash
echo '{"action":"status"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
echo '{"action":"latest","limit":5}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
echo '{"action":"subscribe-test"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
```

`subscribe-test` is a dry-run only. It returns the WebSocket subscription
payloads that would be sent and never opens a socket.

## Non-Goals

- No exchange `/exchange` actions.
- No `clearinghouseState`, user fills, order updates, or other private feeds.
- No wallet private keys or API-wallet management.
- No TradingView webhook or paper-trader critical-path dependency.
