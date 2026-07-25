# Sapphire OS — Quick Start Guide

> First-run setup for new collaborators and operators. Verified 2026-05-03.

---

## Prerequisites

- **macOS 14+** (commander node) or **Windows 11** (GPU node)
- **Python 3.11+**
- **Redis** (event bus)
- **Ollama** (inference mesh T1–T3)
- **Tailscale** (mesh networking)
- **ruff** (lint + format)

```bash
# macOS
brew install python@3.11 redis ruff tailscale

# Start Redis
redis-server --daemonize yes
```

---

## 1. Install

```bash
git clone https://github.com/arigatoexpress/Sapphire.git
cd Sapphire
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pip install -r requirements-test.txt
make install-hooks   # pre-commit + commit-msg
```

---

## 2. Secrets

```bash
cp env.example .env
cp .env.integrations.example .env.integrations

# Required for basic operation
export AUTH_PASSWORD=sapphire
export SAPPHIRE_CONTROL_API_TOKEN=$(openssl rand -hex 32)

# Optional but recommended
export TELEGRAM_BOT_TOKEN=<@BotFather>
export MOONSHOT_API_KEY=<kimi-cloud>
```

Sensitive credentials live in `~/.config/sapphire-secrets/` (mode 0600). Never commit them.

---

## 3. Core Services

### macOS (LaunchAgents — recommended for production)

```bash
# Load all Sapphire LaunchAgents
for f in infra/launchagents/com.sapphire.*.plist; do
    cp "$f" ~/Library/LaunchAgents/
    launchctl load "$f"
done

# Verify
launchctl list | grep sapphire
```

### Manual startup (development)

```bash
# Terminal 1 — Inference proxy (4-tier failover)
python3 services/inference-proxy/app.py

# Terminal 2 — Signal logger
(cd services/alpha && python3 -m uvicorn src.signal_logger:app --port 18081)

# Terminal 3 — Dashboard
(cd services/dashboard && AUTH_PASSWORD=sapphire python3 app.py)

# Terminal 4 — Control plane
(cd services/control-plane && uvicorn app.main:app --port 8082)
```

### Windows (GPU node)

```powershell
# Ollama must run first (OLLAMA_HOST=0.0.0.0)
# Webhook receiver
python services/webhook/app.py

# TradingView CDP agent (requires TV Desktop with --remote-debugging-port=9222)
python services/windows_tv_agent/app.py
```

---

## 4. Health Checks

```bash
# Inference proxy
curl -s http://127.0.0.1:11435/health | python3 -m json.tool

# Signal logger
curl -s http://127.0.0.1:18081/health

# Dashboard
curl -s http://127.0.0.1:8080/healthz

# Public Mission Control (live telemetry)
curl -s https://sapphirealpha.xyz/api/v1/live | python3 -m json.tool

# Full system check
make doctor
```

---

## 5. First Tool invocation

```bash
# Market quote (plugin tool via stdin JSON)
echo '{"action":"quote","symbol":"BTC/USDT"}' | python3 plugins/claw-sapphire/tools/market.py

# Verify state
echo '{"all": true}' | python3 plugins/claw-sapphire/tools/verify.py

# TradingView orchestrator (read-only)
echo '{"action": "list_pine"}' | python3 plugins/claw-sapphire/tools/tradingview.py
```

---

## 6. TradingView Webhook Setup

1. **Configure TradingView Desktop** (Windows):
   ```
   "C:\Users\...\TradingView.exe" --remote-debugging-port=9222
   ```

2. **Set webhook URL** in TradingView alert:
   ```
   http://100.x.x.z:9090/webhook/tradingview
   ```

3. **Test the pipeline**:
   ```bash
   curl -X POST http://100.x.x.z:9090/webhook/tradingview \
     -H "Content-Type: application/json" \
     -d '{"symbol":"BTCUSDT","action":"buy","price":76000,"confidence":0.85}'
   ```

---

## 7. Access Dashboards

| Surface | URL | Auth |
|---|---|---|
| Public face | https://sapphirealpha.xyz | — |
| Live telemetry | https://sapphirealpha.xyz/api/v1/live | — |
| Dashboard | http://localhost:8080/showcase | `sapphire` / `.env` password |
| Control plane | http://localhost:8082 | `SapphireControl` header |
| OpenBB (32 providers) | http://localhost:6900 | — |
| Inference proxy | http://localhost:11435 | — |

---

## 8. Running Tests

```bash
# Fast — unit tests only
make test

# Full — core + plugin
make test-all

# Lint
make lint
make fix    # auto-fix + format

# Mirror CI locally
make ci

# README inventory guard
python3 scripts/ops/test_inventory.py --check-readme
```

> **macOS gotcha:** `python3` may resolve to Homebrew 3.14 (no pytest). Use `/usr/local/bin/python3` or the venv.

---

## 9. Multi-Chain Protocol Access

Sapphire ships read-only typed access to live mainnet protocols across 3 chains:

| Chain | Aave V3 | GMX V2 | Other |
|---|---|---|---|
| MegaETH (4326) | yes ($450M) | yes (6 markets) | Kumbaya DEX, USDM |
| Arbitrum (42161) | yes ($1.06B) | yes (60 markets) | — |
| Optimism (10) | yes ($82M) | — | — |

```python
# Example: read MegaETH Aave V3 reserves
from lib.chains.megaeth.protocols import MegaEthProtocols
proto = MegaEthProtocols()
reserves = proto.aave.get_reserves_data()
```

---

## 10. Common Operations

```bash
# Production readiness sweep
python3 scripts/ops/production_readiness_sweep.py --json

# Content engine (weekly report)
python3 -m lib.content generate
python3 -m lib.content publish

# Backtest sweep
python3 -m lib.analytics.run_strategies --days 90

# TV orchestrator (read-only)
python3 scripts/ops/tradingview_ta_capture.py probe
python3 scripts/ops/tradingview_ta_capture.py sweep --offline --limit 6

# Pine strategy generation + validation
python3 scripts/ops/tradingview_ta_capture.py pine-generate-batch --validate
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard crashes on import | Set `AUTH_PASSWORD` env var |
| Control plane returns 503 | Set `CONTROL_PLANE_TOKEN` — intentional fail-closed |
| Inference proxy timeouts | Check Windows Ollama (`OLLAMA_HOST=0.0.0.0`) and Tailscale |
| Redis events missing | Check `tail -f data/events/bus.jsonl` — JSONL fallback survives Redis outages |
| Tests fail with import errors | Ensure `conftest.py` is present — it patches `sys.path` for legacy imports |
| OpenBB SDK errors | Use REST API at `:6900`; SDK auto-generated files are broken |
| Position sizing = 0 | Check `execution_stage` for typos; unknown-stage defaults to 0 (paper) |

---

## Next Steps

1. Read [`CLAUDE.md`](../CLAUDE.md) — the full project map
2. Read [`docs/architecture-overview.md`](architecture-overview.md) — module wiring
3. Read [`docs/onboarding/collaborator-pack.md`](onboarding/collaborator-pack.md) — security posture, repo layout
4. Check [`docs/routines-manifest.md`](routines-manifest.md) — every scheduled routine

---

*Sapphire OS · [sapphirealpha.xyz](https://sapphirealpha.xyz) · [GitHub](https://github.com/arigatoexpress/Sapphire)*
