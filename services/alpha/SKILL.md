---
name: sapphire-alpha
description: Trading engine — signals, risk, execution, self-improvement loop
type: service
runtime: python
deploy_target: rari1+rari2
dependencies: [sapphire-core, sapphire-telegram]
entry_point: src/main.py
test_command: pytest tests/
---

# services/alpha

Core trading engine. Receives signals from TradingView webhooks, applies risk filters via sapphire-core, executes on Lighter Protocol, and publishes trade events to the event bus.

## Components

- Signal ingestion (TradingView → webhook → alpha)
- Risk kernel (circuit breaker, position sizing, drawdown limits)
- Execution router (Aster DEX + Hyperliquid via rari2)
- Self-improvement: trade metrics → control-plane tasks → agent improvements

## Signal Flow (on-prem)

```
TradingView → webhook.sapphirealpha.xyz (Cloudflare Tunnel)
  → Windows PC:9090 (Ollama enrichment)
  → rari1:18081 + rari2:18081 (Tailscale HTTP, parallel)
  → sapphire-core risk check
  → Redis pub/sub: trading-signals → aster, hyperliquid
  → control-plane:8082 → Telegram notification
```

## Metrics (PnL is king)

- Win rate target: 80%+
- Risk metric: Sortino + Calmar (not Sharpe)
- Max drawdown: 15%
- Pairs: ETH/BTC, SOL/BTC, ZEC/BTC, HYPE/USDT, BTC/USDT

## Deploy (on-prem)

Runs on both rari1 and rari2 (port 18081). See `infra/pi/` for systemd services.
Signal broker: Redis on rari1 (`REDIS_URL=redis://100.x.x.x:6379`).

```bash
# Install Redis on rari1 first:
ssh rari@100.x.x.x 'bash -s' < infra/pi/rari1/setup-redis.sh
# Then deploy control-plane:
bash infra/pi/rari1/deploy-control-plane.sh
```
