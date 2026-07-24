<div align="center">

<img src="docs/brand/kadima-mark-b-quadrilemniscate-300.png" width="118" alt="Sapphire mark"/>

# Sapphire OS

</div>

[![CI](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml)
[![Security](https://github.com/arigatoexpress/Sapphire/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/arigatoexpress/Sapphire/actions/workflows/security.yml)
[![Tests](https://img.shields.io/badge/tests-7%2C351%2B%20passing-2ea44f)](scripts/ops/test_inventory.py)
[![License](https://img.shields.io/badge/license-proprietary-0A2540)](LICENSE)

**A self-sovereign operating system for capital intelligence, autonomous operations, and acquisition-grade diligence.**

It runs trading, on-chain analytics, threat intel, regulatory monitoring, and content ops as one event-bus-mediated system on a four-node Tailscale mesh.

## What this does

Sapphire connects market data, on-chain signals, threat intelligence, and macro regimes into a single brain that publishes a live health score and narrative. It includes a 52-page dashboard, autonomous trading with fail-closed kill switches, an inference proxy with 4-tier failover, and a content engine with a 7-check quality rubric.

## What's new (2026-07)

- **Auto-executor paper lane** — autonomous trading executor bridging confirmation-firewall approvals to paper execution, with exactly-once execution, a single-instance lock, and Telegram-gated approvals (`services/alpha/auto_executor.py`, `com.sapphire.auto-executor` LaunchAgent).
- **TradingView durable webhook pipeline** — Mac-side webhook receiver + Cloudflare Quick Tunnel ingress, durable alert log, idempotent dedup, live dashboard probe, and auto-sync of the Cloud Run `TV_WEBHOOK_URL`.
- **TDR Pro sync** — autonomous podcast/RSS sync pipeline feeding the daily brief and the public dashboard's clips widget.
- **Robinhood Crypto client** — Ed25519-signed REST client (`lib/portfolio/robinhood.py`): accounts, holdings, best bid/ask, order history, reconstructed cost basis.
- **Fleet status monitor** — unified aggregator (`services/pipeline/fleet_status.py`) probing services, LaunchAgents, and the L2 wallet; feeds the daily brief.
- **pm-bot Telegram gate** — PM bot owns Telegram (polling mode with shared-token safety); producer alerts become reviewed local drafts.
- **Brave CDP adapter** — browser automation adapter + auth probes (`lib/sources/brave_browser.py`) for authenticated source capture.
- **Public face** — [sapphire-alpha-dashboard](https://github.com/arigatoexpress/sapphire-alpha-dashboard) is the public, privacy-preserving Mission Control at sapphirealpha.xyz.

## Quick start

```bash
# Requirements: Python 3.11+, Redis, Ollama
pip install -r services/alpha/requirements.txt
pip install -r services/dashboard/requirements.txt

cp env.example .env
cp .env.integrations.example .env.integrations

# Start core services
python3 services/inference-proxy/app.py &                 # :11435
(cd services/alpha && python3 -m uvicorn src.signal_logger:app --port 18081) &
(cd services/dashboard && python3 app.py) &               # :8080
(cd services/control-plane && uvicorn app.main:app --port 8082) &

# Health checks
curl -s http://127.0.0.1:11435/health | python3 -m json.tool
curl -s http://127.0.0.1:18081/health
```

## Architecture

Six concerns share one event bus (Redis Streams + JSONL fallback):

- **Trading**: TradingView Pine → Signal Logger → Risk Kernel → Confirmation Firewall → Paper / Robinhood Crypto / Hyperliquid
- **Intelligence**: On-chain, macro, counter-party, threat, regime, and forecast silos
- **Synthesis**: Brain (`/api/brain/synthesis`) collapses all silos into one health score
- **Content**: 17-module research-to-publish pipeline with rubric gating
- **Security**: SBOM, model SHA-256 verification, network mapper, global kill switch
- **Control**: Telegram PM bot, dashboard, inference proxy

## Key features

- 7 quant strategies + 5 Pine strategies with CPCV backtesting
- Fail-closed trading: $5/order cap, $25/day loss limit, global kill switch
- 4-tier inference mesh (GPU → Pi ×2 → Mac CPU → Kimi Cloud)
- Live Brain synthesis endpoint at `sapphirealpha.xyz/api/brain/synthesis`
- 7,351+ passing tests across 444 files
- 3 Solidity contracts on Robinhood Chain testnet

## Tech stack

Python · FastAPI · Flask · Redis · Ollama · DuckDB · Solidity · Tailscale · GCP · Playwright

## Safety & disclaimers

- **Research/prototype software.** Not financial advice.
- **Paper trading first.** Live trading is capped, kill-switched, and explicitly gated.
- **Fail-closed by default.** If a service, check, or gate fails, the system stops rather than proceeds.
- **No warranty.** See [LICENSE](LICENSE).

## Agent collaborators

See [AGENTS.md](AGENTS.md) for the full agent charter, safety boundaries, and common commands.
