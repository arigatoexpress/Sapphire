# Sapphire OS

Autonomous trading + project-management + intelligence system. Telegram-first, agent-driven, on-prem (Mac + Windows GPU + 2 Raspberry Pis) with GCP as the data lake. Built to optimize

> `Net PnL = (edge × trades × capital efficiency) − (fees + slippage + infra + tail losses)`

under hard downside controls. Three AI "employees" — **SAPPHIRE** (security), **OBSIDIAN** (ops), **EMERALD** (strategy) — operate through the OpenClaw/NemoClaw runtime. The human governance path is a Telegram heartbeat.

## Quick start

```bash
# Python 3.11+, ruff, Redis, Ollama. Mac users: /usr/local/bin/python3 (brew 3.14 lacks pytest).

# 1. Install deps
pip install -r services/alpha/requirements.txt
pip install -r services/dashboard/requirements.txt

# 2. Set secrets
export AUTH_PASSWORD=sapphire             # dashboard basic-auth
export TELEGRAM_BOT_TOKEN=…                # from @BotFather
export MOONSHOT_API_KEY=…                  # optional — Kimi Cloud fallback

# 3. Start core services (all LaunchAgents on Mac, but can run ad-hoc)
python3 services/inference-proxy/app.py &                    # :11435
(cd services/alpha && python3 -m uvicorn src.signal_logger:app --port 18081) &
(cd services/dashboard && python3 app.py) &                  # :8080
(cd services/control-plane && uvicorn app.main:app --port 8082) &

# 4. Health
curl -s http://127.0.0.1:11435/health | jq .
curl -s http://127.0.0.1:18081/health

# 5. Run the plugin tools (all read stdin JSON)
echo '{"action":"quote","symbol":"BTC/USDT"}' | python3 plugins/claw-sapphire/tools/market.py
echo '{"action":"predict"}'                   | python3 plugins/claw-sapphire/tools/predict.py

# 6. Tests
/usr/local/bin/python3 -m pytest tests/unit/ -q
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q

# 7. Lint
ruff check --fix .
```

## Architecture

```
Telegram ── hermes gateway ── inference-proxy (:11435)
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   Windows GPU (RTX 5070 Ti)                    Mac Ollama / Pi / Kimi Cloud

Telegram commands ── services/telegram-bot (:8088) ── claw-code (+ plugins/claw-sapphire)

TradingView ── Windows :9090 ── Mac signal-logger (:18081) ── Redis pub/sub
                                                                  │
                           ┌──────────────────────────────────────┼──────────────────────┐
                           ▼                                      ▼                      ▼
                 services/alpha  (risk kernel)           signal_generator         control-plane (:8082)
                           │                                                              │
                           ▼                                                              ▼
                execution/dispatcher ── aster / hyperliquid                   dashboard (:8080, Flask)

data/ ── services/pipeline/gcp_sync.py ── BigQuery (tho-ai-agent.sapphire.*)
                                      └── GCS (sapphire-data-lake/raw/<source>/YYYY-MM-DD/)
```

See [`docs/architecture-overview.md`](docs/architecture-overview.md) for the full diagram and lifecycles.

## Key features

- **4-tier LLM failover** — Windows GPU → Pi → Mac Ollama → Kimi Cloud. Sensitivity classifier gates Kimi.
- **Autonomous trading loop** — TradingView → signal logger → Redis → risk kernel → execution. Paper portfolio ($100 K, ATR stops, 1.67:1 R:R) runs in parallel.
- **Prediction engine** — 6-factor TA (RSI/MACD/BB/MA/ATR/vol) + Kronos ML, scored nightly. 58 % overall, 75 % on BTC.
- **26-tool plugin** (`plugins/claw-sapphire/`) — dispatch, verify, budget, state, market, predict, paper_trader, threat_intel, research, and 17 more.
- **20 scheduled routines** — morning briefing, trading research, market pulse, threat intel, tests, repo fixes, weekly review. All drive Telegram.
- **Ops dashboard** — 20+ pages (architecture, intelligence, signals, risk, SOC, chain, predictions), 20+ APIs. Basic-auth.
- **GCP data lake** — NDJSON watermark sync to BigQuery + GCS. Source: local JSONL event streams.
- **Risk primitives** — circuit breaker, position sizing (Kelly-informed), execution idempotency, confirmation firewall, sensitivity gate.

## Where things live

| Path | What |
|------|------|
| `services/` | 10 services (alpha, aster, control-plane, dashboard, hyperliquid, inference-proxy, pipeline, scout-sandbox, telegram-bot, webhook) |
| `lib/` | Shared code: `core/` (risk, pub/sub, models), `agents/` (orchestrator), `analytics/`, `telegram/` |
| `plugins/claw-sapphire/` | 26 tools + 9 libs + 2 hooks for the claw-code runtime |
| `pine/` | Pine Script strategies (v1–v3 Ultra) |
| `skills/` | 11 Claude Code skill dirs |
| `tools/` | `pm-commander/` (SwiftUI Mac app), `claude-analytics/`, `flowise/`, `sui_event_scanner/` |
| `infra/` | `cloudflare/`, `docker/`, `migrations/`, `pi/`, `terraform/legacy/`, `windows/` |
| `scripts/` | Top-level ops + `deploy/` (15+) + `loose/` (dev) |
| `data/` | Runtime state (JSONL event log, signals, predictions, portfolio, registries) |
| `tests/` | `unit/`, `integration/`, `legacy/`, `visual-baseline/` |
| `docs/` | Setup guides, architecture overview |

## Full reference

**[`CLAUDE.md`](CLAUDE.md)** — the authoritative operating manual. Module map, all services with ports + LaunchAgent names, all 20 scheduled tasks, inference-proxy model routing, dashboard APIs, gotchas, code conventions. Every future Claude Code session reads it first — keep it current.

## License

See [`LICENSE`](LICENSE).
