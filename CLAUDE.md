# Sapphire OS

Autonomous trading + project management + intelligence system. Telegram-first, agent-driven. Python 3.11+.

## Commands

```bash
# Test
pytest tests/unit/ --tb=short -q           # 1,088 tests (use /usr/local/bin/python3 on Mac)
pytest plugins/claw-sapphire/tests/ -q     # 13 plugin tests

# Lint
ruff check .                               # Uses pyproject.toml rules (E501 ignored)
ruff check --fix .                         # Auto-fix

# Services (Mac — all have LaunchAgents)
uvicorn app.main:app --port 8082           # Control-plane (run from services/control-plane/)
AUTH_PASSWORD=sapphire python3 app.py       # Dashboard (run from services/dashboard/)
python3 services/telegram-bot/app.py --poll # Telegram bot
python3 -m uvicorn src.signal_logger:app --port 18081  # Signal logger (from services/alpha/)

# TradingView MCP (requires TV Desktop with --remote-debugging-port=9222)
tv status                                  # Check CDP connection
tv quote                                   # Live price
tv pine compile                            # Compile Pine Script in editor
tv stream all                              # Stream all panes as JSONL

# OpenBB
curl "http://localhost:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance"

# Sapphire plugin tools
echo '{"action":"quote","symbol":"AAPL"}' | python3 plugins/claw-sapphire/tools/market.py
echo '{"all": true}' | python3 plugins/claw-sapphire/tools/verify.py
python3 plugins/claw-sapphire/tools/budget.py < /dev/null
```

## Module Map

| Path | Type | Description |
|------|------|-------------|
| `lib/core/` | library | Shared: risk kernel, circuit breaker, position sizing, models, logging |
| `lib/telegram/` | library | Telegram bot framework + handlers |
| `lib/agents/` | library | OpenClaw/NemoClaw dispatch, orchestrator, runtime policy |
| `services/alpha/` | service | Trading engine + signal logger [Mac:18081] |
| `services/aster/` | service | Aster DEX trading bot — Solana perps [paused, needs Pi] |
| `services/hyperliquid/` | service | Hyperliquid L1 trading bot [stub, needs Pi] |
| `services/dashboard/` | service | Flask dashboard [Mac:8080, auth: sapphire] |
| `services/control-plane/` | service | PM hub: projects, tasks, events, Kimi bridge [Mac:8082] |
| `services/webhook/` | service | TradingView webhook receiver [Windows:9090] |
| `services/telegram-bot/` | service | NemotronRariBot — thin service, delegates to plugin tools |
| `clients/blanga/` | client | BIS: brokerage intelligence |
| `plugins/claw-sapphire/` | plugin | Claw-code plugin: 7 tools, 2 hooks, 4 libs, 13 tests |
| `pine/` | pine | TradingView strategies (v1-v3 Ultra, 80%+ win rate target) |
| `skills/` | skills | Agent-executable capabilities (10 skills) |
| `tools/pm-commander/` | tool | Sapphire Command — SwiftUI desktop app (7-tab command center) |
| `data/benchmarks/kadima-labs/` | data | Kadima Labs AI benchmark (v1-v3, 70 charts, 30 JSON) |
| `infra/` | infra | Cloudflare Tunnel, Pi systemd, Windows setup |

## Infrastructure (Pi-less since 2026-04-03)

**Mac (100.67.171.79) — runs everything:**
- control-plane:8082, dashboard:8080, signal-logger:18081
- telegram-bot, OpenBB:6900, Redis:6379, Ollama:11434
- Claude Code, claw-code, all MCPs

**Windows PC (100.71.10.48) — GPU + webhook:**
- Ollama:11434 (26 models, RTX 5070 Ti, OLLAMA_HOST=0.0.0.0)
- webhook:9090 (TradingView signal receiver)

**Pis (rari1/rari2) — DECOMMISSIONED.** Pi OS WiFi incompatible. Trading execution paused.

## Code Style

- Python: ruff format, type hints, Google-style docstrings
- TypeScript: strict mode, no `any`
- Every module has a SKILL.md — read it before working on that module
- Services never import from other services — only from `lib/`
- PnL is king. Sortino/Calmar over Sharpe. 80%+ win rate target.

## Satellite Repos (orchestrated, not absorbed)

| Repo | GitHub | Role |
|------|--------|------|
| `~/Code/claw-code` | instructkr/claw-code | Rust agent runtime |
| `~/Code/Project-Go-Forward` | arigatoexpress/Project-Go-Forward | THO client PM |
| `~/Code/regional-intel-workbench` | arigatoexpress/regional-intel-workbench | Intelligence platform |
| `~/Code/tradingview-mcp` | arigatoexpress/tradingview-mcp | TradingView MCP |
| `~/Code/Cointracker` | arigatoexpress/crypto-tax-tracker | Crypto tax engine |

## Sapphire Plugin (v0.3.0, claw-code native)

`plugins/claw-sapphire/` — hooks + tools + libs + tests:
- `sapphire_dispatch` — multi-tier routing (T0 Nemotron free → T1 Kimi → T3 Claude)
- `sapphire_verify` — post-fix lint + test verification
- `sapphire_budget` — real token tracking per tier
- `sapphire_state` — persistent factory memory (backoff on failed fixes)
- `sapphire_status` — mesh device + inference status
- `sapphire_notify` — Telegram via NemotronRariBot
- `sapphire_market` — unified OpenBB + TradingView data

## Inference Fallback Chain

1. **Windows GPU** (100.71.10.48:11434) — Nemotron 3 Nano 196 t/s, Cascade-2 31.6B
2. **Mac Ollama** (localhost:11434) — llama3.3:70b fallback
3. **Cloud API** — claude-sonnet-4 (expensive, architecture only)

## Trading Pipeline

TradingView → webhook (Windows :9090) → signal logger (Mac :18081) → Telegram
Signals logged to `data/trading_signals.jsonl`. Execution paused (needs Pis).

## Event System

JSONL at `data/system_events.jsonl`. Tags: `project:` `agent:` `priority:` `type:` `service:` `device:`
Registries: `data/connectors.json`, `data/device_topology.json`

## Gotchas

- Tests use `importlib` with hardcoded paths — moved from `services/alpha-engine/` to `services/alpha/` (fixed)
- `conftest.py` patches `sys.path` for legacy imports — don't remove it
- Dashboard requires `AUTH_PASSWORD` env var or it crashes on startup
- OpenBB SDK has broken auto-generated package files — use REST API (:6900) instead
- Kimi CLI auth tokens expire in ~1 hour — need frequent `kimi login`
- macOS `python3` may resolve to brew 3.14 (missing pytest) — use `/usr/local/bin/python3` for tests
- GPU Ollama needs SSH restart with `OLLAMA_HOST=0.0.0.0` if Windows reboots before scheduled task runs
