# Sapphire OS

Autonomous trading + project management + intelligence system. Telegram-first, agent-driven. Python 3.11+.

## Commands

```bash
# Test
pytest tests/unit/ --tb=short -q           # 1,273 passing + 1 skipped (use /usr/local/bin/python3 on Mac)
pytest plugins/claw-sapphire/tests/ -q     # 25 plugin tests (budget, router, state, technical_analysis)

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

## Infrastructure (verified 2026-04-18)

**Mac (100.67.171.79) — commander, all services:**
- control-plane:8082, dashboard:8080, signal-logger:18081
- inference-proxy:11435 (4-tier failover: GPU→Pi→Mac→Kimi, threaded, /metrics endpoint)
- hermes-agent gateway (ai.hermes.gateway LaunchAgent, Telegram bot)
- OpenBB:6900, Redis:6379, Ollama:11434 (6 models)
- regional-intel:8787 (vote monitor + intelligence console)

**Windows PC (100.71.10.48) — GPU + services:**
- Ollama:11434 (28 models, RTX 5070 Ti 16GB VRAM, OLLAMA_HOST=0.0.0.0)
- OLLAMA_MODELS=D:\OllamaModels set at Machine scope (required — SYSTEM service doesn't inherit user env)
- webhook:9090, telemetry-dashboard:3001, OllamaServe (auto-start)
- SSH: `ssh aribs@100.71.10.48`

**Pi rari1 (100.120.191.1) — ONLINE** (Tailscale): Ollama:11434 serves nemotron-mini, smollm2:1.7b, qwen2.5:0.5b, gemma2:2b. SSH port 22 refused — needs physical access to start sshd. Proxy routing disabled by default (`PI_RARI1_ENABLED=0`); set to `1` after the Pi is stable.
**Pi rari2 (100.87.225.89) — ONLINE** (as of 2026-04-18): Ollama:11434 serves nemotron-mini, gemma2:2b, smollm2:1.7b, qwen2.5:0.5b. Previously marked OFFLINE in the proxy — `inference-proxy/app.py:148` comment + CLAUDE.md were stale. `PI_RARI2_ENABLED=1` to route.

## Agent Workflow Discipline (Karpathy Principles)

These apply to every coding task in this repo. They bias toward caution over speed — use judgment for trivial tasks.

**1. Think Before Coding** — State assumptions explicitly. If multiple interpretations exist, surface them before implementing. If unclear, stop and ask. Never hide confusion.

**2. Simplicity First** — Minimum code that solves the problem. No speculative features, no abstractions for single-use code, no unasked-for "flexibility". If 200 lines could be 50, rewrite it.

**3. Surgical Changes** — Touch only what the request requires. Don't refactor adjacent code, don't "improve" formatting, don't delete pre-existing dead code unless asked. Every changed line must trace directly to the request.

**4. Goal-Driven Execution** — Transform tasks into verifiable success criteria before starting. For multi-step tasks, state a brief plan with verification steps:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Source: `andrej-karpathy-skills` — `~/Code/Sapphire/lib/core/src/sapphire_core/task_discipline.py`

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

## Sapphire Plugin (v0.3.0 — 30 tools on disk, 7 registered in plugin.json)

`plugins/claw-sapphire/plugin.json` declares **7** as Claude Code tools: `sapphire_dispatch`, `sapphire_verify`, `sapphire_budget`, `sapphire_state`, `sapphire_status`, `sapphire_notify`, `sapphire_market`. The other 23 are standalone scripts invoked via stdin JSON (by hermes skills, scheduled tasks, other tools). plugin.json version reads 0.3.0; update to 0.4.0 when registering more.

`plugins/claw-sapphire/tools/` — all 30 invoked via stdin JSON:
- **Registered (7):** `dispatch`, `verify`, `budget`, `state`, `status`, `notify`, `market`
- **Intel / analytics (9):** `threat_intel`, `starred_repos`, `vote_monitor`, `health_check`, `watchdog`, `digest`, `research`, `events`, `qa_aware_factory`
- **Trading (9):** `predict` (6-factor TA, **verified 58% overall, BTC 75%, ETH 62%, SOL 38% on 24 scored predictions**), `predict_kronos` (Kronos-base forecasting; `kronos_predict.py` is a legacy duplicate), `signal_generator`, `paper_trader`, `crypto_portfolio`, `backtest`, `macro_data` (crashes without FRED key), `trading_brain`, `market_sentiment`
- **Other (5):** `lumo` + `lumo_research` (Lumo-T5 cyber research), `tho_intel`, `lead_engine`, `kronos_predict` (legacy — prefer `predict_kronos`)

**Orphan tools: `trading_brain`, `lead_engine`, `tho_intel`, `macro_data`, `lumo` (not imported by any service or scheduled task — invoke directly or wire them).**

`plugins/claw-sapphire/lib/` — 10 shared modules (was "4 libs" in old CLAUDE.md):
- `technical_analysis.py` — RSI, MACD, Bollinger, MA, ATR, volume (from OpenBB OHLCV)
- `nemotron.py` — Ollama client with failover (proxy → GPU → Mac)
- `quant_analysis.py` — S/R detection, correlation, trend strength
- `router.py`, `runtime_policy.py`, `token_governor.py` — dispatch policy + budget
- `sensitivity_classifier.py` — PII/secret regex (used by dispatch, not proxy)
- `market_data.py`, `nvidia_agents.py` — shared market + NeMo helpers

## Inference Proxy (localhost:11435)

4-tier failover (threaded server — concurrent requests safe). hermes-agent and all plugin tools talk to this.
- **T1 Windows GPU** (100.71.10.48:11434): native `/api/chat` (NOT `/v1/` — returns empty on Windows). ~0.4s.
- **T2 Pi rari1** (100.120.191.1:11434): nemotron-mini, smollm2, qwen2.5:0.5b, gemma2:2b. `PI_RARI1_ENABLED=1`. Currently failing all proxy probes (0/4 success in `/metrics`) despite responding to direct curl — routing config bug; investigate before relying on it.
- **T2 Pi rari2** (100.87.225.89:11434): ONLINE as of 2026-04-18 (5 models). `PI_RARI2_ENABLED=1`. Proxy comment at `app.py:148` still says "rari2 is offline" — stale.
- **T3 Mac local** (127.0.0.1:11434): `/v1/chat/completions` passthrough. ~90s (CPU inference).
- **T4 Kimi Cloud** (api.moonshot.cn): non-sensitive only. `MOONSHOT_API_KEY` loaded from `~/.sapphire/secrets.env` (mode 0600, not in plist).
- Model aliases: `fast`/`quick`→nemotron-mini:latest, `auto`/`balanced`→hermes3:8b, `deep`→qwen3:14b, `code`→gemma4:latest, `reason`→deepseek-r1:14b, `qwen-reason`→qwen3.5:9b, `cascade`/`moe`→nemotron-cascade-2, `large`→qwen2.5:32b, `kimi`→kimi-cloud
- GPU-only models (>8B params): Windows only, 503 if GPU down
- Sensitivity gate: regex blocks api_key/password/jwt/SSN/CC from T4
- Health: 60s cooldown, background 30s probe, `/metrics` endpoint
- Endpoints: `/health`, `/metrics`, `/v1/chat/completions`, `/v1/models`

## Trading Pipeline

TradingView → webhook (Win :9090) → signal logger (Mac :18081) → Telegram
Autonomous signal generator scans RSI/MACD/BB/MA → generates signals → paper trades
Paper portfolio: $100K, ATR-based SL/TP (1.67:1 R:R), 10% position sizing
Prediction accuracy: 58% overall, BTC 75%

## Hermes Agent (Telegram Bot)

hermes-agent (NousResearch) replaced custom bot. Installed at ~/.hermes/.
- Config: ~/.hermes/config.yaml (model: hermes3:8b, provider: custom, base_url: proxy)
- Env: ~/.hermes/.env (TELEGRAM_BOT_TOKEN, OPENAI_BASE_URL → proxy)
- Skills: ~/.hermes/skills/sapphire/ (14 skills: cyber-intel, inference-tier, kimi-delegate, macro-data, paper-trading, regional-intel, repo-discovery, system-health, system-ops, tho-operations, threat-intel, trading-analysis, trading-brain, trading-signals)
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

## 20 Scheduled Tasks (Claude Code)

All in ~/.claude/scheduled-tasks/. Run 24/7 when Claude Code is open. Add `lead-generation` and `pull-gcp-secrets` to the list below; the 18 named tasks cover the rest.
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
