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
| `services/telegram-bot/` | service | Legacy bot (replaced by hermes-agent gateway) |
| `services/inference-proxy/` | service | Multi-model failover proxy [Mac:11435] → Windows GPU / Mac Ollama |
| `clients/blanga/` | client | BIS: brokerage intelligence |
| `plugins/claw-sapphire/` | plugin | Claw-code plugin: 7 tools, 2 hooks, 4 libs, 13 tests |
| `pine/` | pine | TradingView strategies (v1-v3 Ultra, 80%+ win rate target) |
| `skills/` | skills | Agent-executable capabilities (10 skills) |
| `tools/pm-commander/` | tool | Sapphire Command — SwiftUI desktop app (7-tab command center) |
| `data/benchmarks/kadima-labs/` | data | Kadima Labs AI benchmark (v1-v3, 70 charts, 30 JSON) |
| `infra/` | infra | Cloudflare Tunnel, Pi systemd, Windows setup |

## Infrastructure (Pi-less since 2026-04-03)

**Mac (100.67.171.79) — commander, all services:**
- control-plane:8082, dashboard:8080, signal-logger:18081
- inference-proxy:11435 (multi-model failover: GPU→Mac + tier routing)
- hermes-agent gateway (ai.hermes.gateway LaunchAgent, Telegram bot)
- OpenBB:6900, Redis:6379, Ollama:11434 (5 models)
- regional-intel:8787 (vote monitor + intelligence console)

**Windows PC (100.71.10.48) — GPU + services:**
- Ollama:11434 (26 models, RTX 5070 Ti 16GB VRAM, OLLAMA_HOST=0.0.0.0)
- webhook:9090 (SapphireWebhook — TradingView → Mac signal logger)
- telemetry-dashboard:3001 (SapphireDashboard — React + WebSocket real-time viz)
- OllamaServe (auto-start on login)
- All repos mirrored to E:\Sapphire\Code\ (SSH key: sapphire-windows)
- SSH: `ssh aribs@100.71.10.48` (ed25519 key on GitHub)

**Pis (rari1/rari2) — DECOMMISSIONED.** Pi OS WiFi incompatible.

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
| `~/Code/cyber-threat-bot` | arigatoexpress/cyber-threat-bot | Threat intel: CISA KEV, NVD, MITRE ATT&CK, revenue synthesis |
| `~/Code/hermes-agent` | NousResearch/hermes-agent | Conversational AI framework (Telegram bot) |

## Sapphire Plugin (v0.4.0 — 21 tools)

`plugins/claw-sapphire/tools/` — all invoked via stdin JSON:
- `dispatch` — multi-tier routing (T0 Nemotron → T3 Claude)
- `verify` — post-fix lint + test verification
- `budget` — real token tracking per tier
- `state` — persistent factory memory (backoff on failed fixes)
- `status` — mesh device + inference status
- `notify` — Telegram alerts via NemotronRariBot (`python3 notify.py "msg" --priority p0`)
- `market` — unified OpenBB + TradingView data
- `threat_intel` — CISA KEV + NVD + MITRE ATT&CK (via ~/Code/cyber-threat-bot)
- `starred_repos` — GitHub starred/trending repo synergy finder
- `vote_monitor` — ve Vote escrow bridge (Blackhole, Supernova, Full Sail)
- `health_check` — 20-point ecosystem health (services, repos, data, inference)
- `watchdog` — smart Telegram alerts on failures/recoveries (deduped, tracks state)
- `predict` — 6-factor TA predictions (RSI, MACD, BB, MA, ATR, volume). 58% accuracy.
- `signal_generator` — autonomous TA scanner → signals + Telegram. Triggers on RSI/MACD/BB.
- `paper_trader` — $100K paper portfolio, ATR stops, Sortino/drawdown metrics
- `crypto_portfolio` — unified view (Cointracker + paper trader + live prices)
- `research` — nightly trading research + prediction scoring
- `digest` — intelligence digest
- `backtest` — Pine Script backtesting
- `qa_aware_factory` — QA-driven factory prioritization
- `events` — system event logging

`plugins/claw-sapphire/lib/` — shared libraries:
- `technical_analysis.py` — RSI, MACD, Bollinger, MA, ATR, volume (from OpenBB OHLCV)
- `nemotron.py` — Ollama client with failover (proxy → GPU → Mac)
- `quant_analysis.py` — S/R detection, correlation, trend strength

## Inference Proxy (localhost:11435)

Smart failover + multi-model routing. hermes-agent and all tools talk to this.
- Windows GPU: uses native `/api/chat` (NOT `/v1/` — it returns empty on Windows Ollama)
- Mac: uses `/v1/chat/completions` (works natively)
- Model tier aliases: `fast`→nemotron-mini, `balanced`→hermes3:8b, `deep`→qwen3:14b,
  `code`→qwen2.5-coder:14b, `reason`→deepseek-r1:14b, `large`→qwen2.5:32b
- GPU-only models (>8B) forced to Windows, skip Mac fallback
- Health tracking: failed endpoints get 60s cooldown before retry

## Trading Pipeline

TradingView → webhook (Win :9090) → signal logger (Mac :18081) → Telegram
Autonomous signal generator scans RSI/MACD/BB/MA → generates signals → paper trades
Paper portfolio: $100K, ATR-based SL/TP (1.67:1 R:R), 10% position sizing
Prediction accuracy: 58% overall, BTC 75%

## Hermes Agent (Telegram Bot)

hermes-agent (NousResearch) replaced custom bot. Installed at ~/.hermes/.
- Config: ~/.hermes/config.yaml (model: hermes3:8b, provider: custom, base_url: proxy)
- Env: ~/.hermes/.env (TELEGRAM_BOT_TOKEN, OPENAI_BASE_URL → proxy)
- Skills: ~/.hermes/skills/sapphire/ (6 skills: threat-intel, trading, health, THO, repos, paper-trading)
- Gateway: ai.hermes.gateway LaunchAgent (always-on Telegram polling)
- Restart: `~/.local/bin/hermes gateway restart`

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
- Windows Ollama `/v1/` endpoint returns empty responses — proxy uses native `/api/chat` and translates
- THO `gcloud run deploy` uses `.gcloudignore` (NOT `.gitignore`) — `tho_documents/` must be included
- THO Cloud Run filesystem is read-only — generated docs go to `/tmp` then GCS
- Express 5 wildcard route: use `/{*path}` not `*` (Windows telemetry-dashboard)
- Windows SSH: `ssh aribs@100.71.10.48` (user is `aribs`, NOT `aspec`)
- cyber-threat-bot: run with `PYTHONPATH=src python3 -m cyber_threat_bot ...` (editable install unreliable)
- regional-intel-workbench venv has stale shebang paths — use `.venv/bin/python -m uvicorn` not `.venv/bin/uvicorn`

## 19 Scheduled Tasks (Claude Code)

All in ~/.claude/scheduled-tasks/. Run 24/7 when Claude Code is open.
- morning-briefing (8 AM) — 6-section digest → Telegram
- trading-research (5:42 AM) — TA predictions + scoring
- market-pulse (8/12/4 M-F) — signal scan + paper trade stops + scoring
- threat-intel-sweep (6:30 AM + 2 PM) — CISA/NVD scan → Telegram on criticals
- github-discovery (7 AM) — star sync + trending repos
- tho-production-healthcheck (*/2h) — watchdog → Telegram alerts
- tho-test-writer (11 AM + 11 PM) — grow test coverage
- creative-experimenter (2 AM) — nightly R&D
- factory-test-guardian (3 AM + 3 PM) — run all test suites
- factory-repo-fixer (*/6h) — auto-fix lint
- code-quality-sweep (1 PM) — dead code, imports
- evening-digest (6 PM) — daily summary
- self-improvement (8:53 PM) — priorities + quality
- sapphire-ci-monitor (*/3h) — lint + test across repos
- factory-client-delivery (10 AM M-F) — THO production check
- vote-monitor-collector (*/4h) — DeFi pool snapshots
- dependency-security-scan (Wed 4 AM) — vuln + secret scan
- sapphire-weekly-review (Sun 9 AM) — architecture audit
