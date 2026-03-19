---
name: sapphire-alpha
description: Trading engine — signals, risk, execution, self-improvement loop
type: service
runtime: python
deploy_target: cloud-run
dependencies: [sapphire-core, sapphire-telegram]
entry_point: src/main.py
test_command: pytest tests/
---

# services/alpha

Core trading engine. Receives signals from TradingView webhooks, applies risk filters via sapphire-core, executes on Lighter Protocol, and publishes trade events to the event bus.

## Components

- Signal ingestion (TradingView → webhook → alpha)
- Risk kernel (circuit breaker, position sizing, drawdown limits)
- Execution router (Lighter Protocol via rari2, future: Hyperliquid, Aster)
- Self-improvement: trade metrics → control-plane tasks → agent improvements

## Signal Flow

```
TradingView → services/webhook → services/alpha → sapphire-core risk check
  → Lighter Protocol (rari2) → event: type:trading, project:sapphire
  → control-plane → Telegram notification
```

## Metrics (PnL is king)

- Win rate target: 80%+
- Risk metric: Sortino + Calmar (not Sharpe)
- Max drawdown: 15%
- Pairs: ETH/BTC, SOL/BTC, ZEC/BTC, HYPE/USDT, BTC/USDT

## Deploy

```bash
gcloud run deploy sapphire-alpha --source . --project sapphire-479610
```
