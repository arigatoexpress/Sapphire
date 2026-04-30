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
- `GET /api/tradingview/ta-machine` returns the dynamic Sapphire TradingView
  TA machine plan: ranked watchlist, indicator stack, chart layout, chart
  readback commands, pair-analysis work orders, and alert JSON template.
- `GET /api/tradingview/watchlist.txt` returns a TradingView-compatible TXT
  export for the current dynamic Sapphire watchlist. The body is
  exchange-prefixed and comma-separated so it can be reviewed/imported into
  TradingView.
- `GET /api/trading/workbench/watchlist` returns the stable read-only workbench
  contract for agents: canonical symbols, TradingView symbols, venue status,
  priorities, source labels, and blocked action list.
- `POST /api/trading/workbench/work-orders/preview` returns preview-only
  TA/chart work orders for requested symbols, timeframes, jobs, and strategies.
  It never posts to webhooks, mutates TradingView, sends Telegram, or submits
  trades.
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
- TradingView watchlist import expects a `.txt` file containing
  exchange-prefixed comma-separated symbols. Sapphire's watchlist export keeps
  this exact shape and does not require live TradingView mutation.
- TradingView strategy placeholders such as `{{ticker}}`,
  `{{strategy.order.action}}`, `{{strategy.order.contracts}}`, and
  `{{strategy.market_position}}` are represented in the lab alert template.
- The TA machine treats TradingView Desktop/CDP commands as operator-control
  automation. Reading chart state, OHLCV summaries, indicator values, Pine
  tables/labels/lines, and screenshots is safe. Adding symbols to the actual
  watchlist, changing panes, adding indicators, injecting Pine, or editing
  alerts remains gated by explicit operator intent.
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

## TradingView TA Machine

Generate the current dynamic plan from the command line:

```bash
python3 scripts/ops/tradingview_ta_machine.py \
  --offline \
  --watchlist-out /tmp/sapphire-tradingview-watchlist.txt \
  --json-out /tmp/sapphire-tradingview-ta-machine.json \
  --print-commands
```

The generated plan ranks Sapphire-liked and trending tokens, emits the
TradingView TXT watchlist body, and creates per-symbol chart work orders using
the local `tv` CLI vocabulary:

- `tv watchlist add <symbol>` — operator-gated watchlist mutation.
- `tv symbol <symbol>` and `tv timeframe <tf>` — operator-gated chart rotation.
- `tv indicator add "<full indicator name>"` — operator-gated TA stack setup.
- `tv ohlcv --summary`, `tv values`, `tv data lines/labels/tables`, and
  `tv screenshot -r chart` — readback evidence for automated TA review.

Actual watchlist mutation is disabled unless `SAPPHIRE_TV_MUTATION_ENABLED=1`
and `--apply-watchlist` are both present. This makes the default path a
reviewable export while still giving Sapphire an explicit bridge into the
operator's TradingView Desktop workbench.

Agent-facing workbench APIs use explicit preview/read-only schemas:

```bash
curl -s http://127.0.0.1:8080/api/trading/workbench/watchlist?offline=1 \
  | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8080/api/trading/workbench/work-orders/preview \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["BTCUSDT","ETH-USD"],"timeframes":["60","240","D"],"dry_run":true}' \
  | python3 -m json.tool
```

The preview endpoint always returns `execution_enabled=false`; requested
browser, Telegram, webhook, or trading mutations appear as blocked actions
unless a separate operator-gated tool explicitly executes them.
