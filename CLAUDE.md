# Sapphire OS

Autonomous trading + intelligence + content ops. Telegram-first, agent-driven, event-bus mediated. Python 3.11+.

## Commands

```bash
# Test
pytest tests/unit/ --tb=short -q           # 1,606 passing + 1 skipped (use /usr/local/bin/python3 on Mac)
pytest plugins/claw-sapphire/tests/ -q     # 25 plugin tests (budget, router, state, technical_analysis)

# Lint
ruff check .                          # pyproject.toml rules (E501 ignored)
ruff check --fix .                    # auto-fix

# Services (Mac — LaunchAgents in infra/launchagents/)
uvicorn app.main:app --port 8082                             # control-plane (from services/control-plane/)
AUTH_PASSWORD=sapphire python3 app.py                        # dashboard (from services/dashboard/)
python3 -m uvicorn src.signal_logger:app --port 18081        # signal logger (from services/alpha/)
X402_ENABLED=1 python3 services/inference-proxy/app.py       # inference proxy with x402 paywall

# TradingView MCP (requires TV Desktop w/ --remote-debugging-port=9222)
tv status && tv quote && tv pine compile && tv stream all

# OpenBB
curl "http://localhost:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance"

# Sapphire plugin tools (stdin JSON)
echo '{"action":"quote","symbol":"AAPL"}' | python3 plugins/claw-sapphire/tools/market.py
echo '{"all": true}' | python3 plugins/claw-sapphire/tools/verify.py

# Content engine
python3 -m lib.content generate                               # render weekly report from events+signals
python3 -m lib.content publish                                # promote draft → ready/
```

## Architecture at a Glance

```
┌─ signal_pipeline ─┐   ┌─ correlation ─┐   ┌─ threat_intel ─┐   ┌─ chain/intelligence ─┐
│ signal.generated  │   │ correlation.  │   │ threat.        │   │ chain.regime.shift    │
│ signal.closed     │   │  broken       │   │  detected      │   │ chain.funding.skew    │
└────────┬──────────┘   └──────┬────────┘   └───────┬────────┘   └───────────┬───────────┘
         │                     │                    │                         │
         └─────────────────────┴────── event_bus ────┴─────────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
        dashboard SSE            content engine               Telegram alerts
       /api/events/stream       (weekly report gen)          (priority-tagged)
```

Event bus: Redis Streams primary → JSONL file fallback (`data/events/bus.jsonl`, survives Redis outage).

## Module Map

| Path | Type | Description |
|------|------|-------------|
| `lib/core/` | library | Risk kernel, circuit breaker, position sizing, models, logging, pubsub, **event_bus** |
| `lib/payments/` | library | **x402 HTTP 402 micropayment middleware** (Flask + raw-socket gates, EVM signatures) |
| `lib/chain/` | library | **On-chain intelligence**: regime, funding, OI, TVL, stablecoin supply, whale flow |
| `lib/content/` | library | **Content engine**: weekly report generator, outreach, quality gate, publisher (Substack/X/LinkedIn/Typefully) |
| `lib/analytics/` | library | CPCV, regime GMM, VPIN, backtest engine, risk engine, liquidation, correlation, **strategy_performance** (× timeframe aggregator), **backtest_results** (sweep reader), **forecast** (Kronos+TA consensus) |
| `lib/agents/` | library | OpenClaw/NemoClaw dispatch, orchestrator, runtime policy, token governor |
| `lib/telegram/` | library | Telegram bot framework + handlers |
| `lib/intel/` | library | Lead enrichment, threat feed aggregation |
| `lib/portfolio/` | library | Robinhood integration, portfolio state |
| `lib/trading/` | library | Strategy runtime, signal enhancer, self-optimizer |
| `services/alpha/` | service | Trading engine + signal logger [Mac:18081] |
| `services/aster/` | service | Aster DEX bot — Solana perps (paused) |
| `services/hyperliquid/` | service | Hyperliquid L1 bot (stub) |
| `services/dashboard/` | service | Flask dashboard [Mac:8080, auth:sapphire] — SSE event stream, content page, metrics |
| `services/control-plane/` | service | PM hub: projects, tasks, events, Kimi bridge [Mac:8082] |
| `services/inference-proxy/` | service | 4-tier LLM failover [Mac:11435] + **x402 gate** |
| `services/pipeline/` | service | GCP sync — syncs events → GCS/BigQuery (hourly watermark; `gcp_sync.py` only, not a daemon) |
| `services/intelligence/` | service | Daily brief generator, chain refresh |
| `services/scout-sandbox/` | service | External-collaborator least-privilege sandbox |
| `services/webhook/` | service | TradingView webhook receiver [Windows:9090] |
| `services/telegram-bot/` | service | Legacy bot (replaced by hermes-agent gateway) |
| `plugins/claw-sapphire/` | plugin | Claw-code plugin: 32 tools + 10 libs + 25 tests |
| `pine/` | pine | TradingView strategies (v1-v3 Ultra, 80%+ win rate target) |
| `skills/` | skills | Agent-executable capabilities |
| `data/content/` | data | Content engine drafts + ready/ queue |
| `data/benchmarks/kadima-labs/` | data | Kadima Labs AI benchmark (v1-v3) |
| `infra/launchagents/` | infra | macOS LaunchAgent plists (incl. content-engine) |

## Infrastructure (verified 2026-04-18)

**Mac (100.67.171.79) — commander, all services:**
- control-plane:8082, dashboard:8080, signal-logger:18081
- inference-proxy:11435 (4-tier failover)
- hermes-agent gateway (ai.hermes.gateway LaunchAgent, Telegram bot)
- content-engine (com.sapphire.content-engine LaunchAgent, weekly cadence)
- OpenBB:6900, Redis:6379, Ollama:11434

**Windows PC (100.71.10.48) — GPU + services:**
- Ollama:11434 (28 models, RTX 5070 Ti 16GB VRAM, OLLAMA_HOST=0.0.0.0)
- OLLAMA_MODELS=D:\OllamaModels set at Machine scope (required — SYSTEM service doesn't inherit user env)
- webhook:9090, telemetry-dashboard:3001, OllamaServe (auto-start)
- SSH: `ssh aribs@100.71.10.48`

**Pi rari1 (100.120.191.1) — ONLINE** (Tailscale): Ollama:11434 serves nemotron-mini, smollm2:1.7b, qwen2.5:0.5b, gemma2:2b. SSH port 22 refused — needs physical access to start sshd. Proxy routing disabled by default (`PI_RARI1_ENABLED=0`); set to `1` after the Pi is stable.
**Pi rari2 (100.87.225.89) — ONLINE** (as of 2026-04-18): Ollama:11434 serves nemotron-mini, gemma2:2b, smollm2:1.7b, qwen2.5:0.5b. Previously marked OFFLINE in the proxy — `inference-proxy/app.py:148` comment + CLAUDE.md were stale. `PI_RARI2_ENABLED=1` to route.

## Sapphire Plugin (32 tool scripts on disk, 12 registered)

`plugins/claw-sapphire/` contains 12 Claude Code tools registered in `plugin.json` plus companion stdin-JSON scripts under `plugins/claw-sapphire/tools/`.

**Infra / ops**: `dispatch`, `verify`, `budget`, `state`, `status`, `notify`, `health_check`, `watchdog`, `events`

**Market / trading**: `market`, `predict`, `predict_kronos`, `signal_generator`, `paper_trader`, `backtest`, `crypto_portfolio`, `trading_brain`, `market_sentiment`, `macro_data`

**Intelligence**: `threat_intel`, `starred_repos`, `vote_monitor`, `tho_intel`, `research`, `digest`, `qa_aware_factory`

**Outreach**: `lead_engine`

**Legacy compatibility alias**: `kronos_predict` delegates to `predict_kronos`

`plugins/claw-sapphire/lib/` — shared libraries:
- `technical_analysis.py` — RSI, MACD, Bollinger, MA, ATR, volume
- `nemotron.py` — Ollama client with failover
- `quant_analysis.py` — S/R detection, correlation, trend strength
- `sensitivity_classifier.py` — multi-group regex, blocks sensitive text from leaving mesh


## Code Style

- Python: ruff format, type hints, Google-style docstrings
- TypeScript: strict mode, no `any`
- Every module has a SKILL.md — read before working on that module
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
| `~/Code/cyber-threat-bot` | arigatoexpress/cyber-threat-bot | Threat intel feeds |
| `~/Code/hermes-agent` | NousResearch/hermes-agent | Conversational framework (Telegram bot) |
| `~/Code/kimi-tools` | local | Kimi Cloud HTTP client |

## Sapphire Plugin (v0.6.0 — 32 tools on disk, 12 registered in plugin.json)

`plugins/claw-sapphire/plugin.json` declares **12** as Claude Code tools: `sapphire_dispatch`, `sapphire_verify`, `sapphire_budget`, `sapphire_state`, `sapphire_status`, `sapphire_notify`, `sapphire_health_check`, `sapphire_market`, `sapphire_predict_kronos`, `sapphire_threat_intel`, `sapphire_lumo_research`, `sapphire_starred_repos`. The other 20 are standalone scripts invoked via stdin JSON (by hermes skills, scheduled tasks, dashboards, or other tools).

`plugins/claw-sapphire/tools/` — all 32 invoked via stdin JSON:
- **Registered (12):** `dispatch`, `verify`, `budget`, `state`, `status`, `notify`, `health_check`, `market`, `predict_kronos`, `threat_intel`, `lumo_research`, `starred_repos`
- **Intel / analytics (6):** `vote_monitor`, `watchdog`, `digest`, `research`, `events`, `qa_aware_factory`
- **Trading (8):** `predict` (6-factor TA, **verified 58% overall, BTC 75%, ETH 62%, SOL 38% on 24 scored predictions**), `signal_generator`, `paper_trader`, `crypto_portfolio`, `backtest`, `macro_data` (graceful error when FRED key is missing), `trading_brain`, `market_sentiment`
- **Other (5 + 1 legacy alias):** `lead_engine`, `lead_enrich`, `lumo`, `tho_intel`, `solana_wallet`, `kronos_predict` (legacy wrapper — prefer `predict_kronos`)

**Repo-local orphan entrypoints: `trading_brain`, `tho_intel`, `lumo`. `lead_engine` and `macro_data` still have in-repo tool-graph callers.**

`plugins/claw-sapphire/lib/` — 10 shared modules (was "4 libs" in old CLAUDE.md):
- `technical_analysis.py` — RSI, MACD, Bollinger, MA, ATR, volume (from OpenBB OHLCV)
- `nemotron.py` — Ollama client with failover (proxy → GPU → Mac)
- `quant_analysis.py` — S/R detection, correlation, trend strength
- `router.py`, `runtime_policy.py`, `token_governor.py` — dispatch policy + budget
- `sensitivity_classifier.py` — PII/secret regex (used by dispatch, not proxy)
- `market_data.py`, `nvidia_agents.py` — shared market + NeMo helpers

## 20 Scheduled Tasks (Claude Code, `~/.claude/scheduled-tasks/`)

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

## Performance Analytics (2026-04-19)

`/performance` dashboard page is fully wired to real trade data via four endpoints:

- `GET /api/strategy-performance` — `lib.analytics.strategy_performance.report()`. Unified trade stream (data/signals/\*.jsonl + data/performance/signals.jsonl + data/paper_portfolio.json history, deduplicated by key). Returns overall / by_strategy / by_timeframe / by_strategy_timeframe / by_symbol. Timeframe buckets by hold duration: 1h, 4h, 1d, 7d, 30d, all. Per-bucket metrics: trades, win_rate, total_pnl_usd, avg_pnl_usd, best/worst, profit_factor, sortino, avg_roi_pct, portfolio_roi_pct.
- `GET /api/performance-timeseries` — `lib.analytics.strategy_performance.timeseries()`. Equity curve (cumulative P&L per closed trade, anchored to paper_portfolio.json initial_capital), drawdown series (running peak), monthly returns (year/month grid). Powers the SVG charts + monthly grid.
- `GET /api/backtest-results?metric={sortino|sharpe|calmar|total_return_pct|win_rate|profit_factor}&limit=10` — `lib.analytics.backtest_results.summary()` + `leaderboard()`. Reads latest strategy_sweep_\*.json / best_per_symbol_\*.json artifacts under `data/backtests/strategies/`, sanitizes `Infinity`/`NaN` (strict-JSON-safe), filters rows with <5 trades by default.
- `GET /api/forecast` — `lib.analytics.forecast.forecast()`. Reconciles Kronos OHLCV projections (`data/intelligence/<date>/predictions.json`) with TA-scanner predictions (`data/trading_predictions.jsonl`, <36h old), aliases BTC-USD↔BTC etc. Emits `consensus` (AGREE_BULL|AGREE_BEAR|CONTRADICT|PARTIAL|KRONOS_ONLY|TA_ONLY|NEITHER) and `edge_score` (blended EV in [-1,+1]).

The performance.html template was previously hardcoded demo data (fake "Ultra v3 Momentum" strategies, fake $12,847 P&L). All panels now fetch the above endpoints on load + every 60s.

Tests at `tests/unit/test_strategy_performance.py`, `test_backtest_results.py`, `test_forecast.py` (57 tests). To regenerate a backtest sweep: `python3 -m lib.analytics.run_strategies --days 90` — note: currently blocked by a signature-drift bug in `Backtester.__init__` where `strategies.py` passes `fee_bps` that `backtest.py` no longer accepts. The Apr-18 artifacts remain valid for the leaderboard until that is refactored.

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
- market-pulse (8/12/4 M-F) — signal scan + paper trade stops
- threat-intel-sweep (6:30 AM + 2 PM) — CISA/NVD
- github-discovery (7 AM) — star sync + trending
- tho-production-healthcheck (*/2h) — watchdog
- tho-test-writer (11 AM + 11 PM) — coverage growth
- creative-experimenter (2 AM) — nightly R&D
- factory-test-guardian (3 AM + 3 PM) — all test suites
- factory-repo-fixer (*/6h) — auto-fix lint
- code-quality-sweep (1 PM) — dead code, imports
- evening-digest (6 PM) — daily summary
- self-improvement (8:53 PM) — priorities
- sapphire-ci-monitor (*/3h) — lint + tests
- factory-client-delivery (10 AM M-F) — THO production
- vote-monitor-collector (*/4h) — DeFi pool snapshots
- dependency-security-scan (Wed 4 AM) — vuln + secrets
- sapphire-weekly-review (Sun 9 AM) — architecture audit
- **lead-generation** (daily) — autonomous outreach (new)
- **pull-gcp-secrets** — GCP secret sync

## Gotchas

- `conftest.py` patches `sys.path` for legacy imports — don't remove it.
- Dashboard requires `AUTH_PASSWORD` env var or it crashes on import.
- Control-plane fails closed (HTTP 503) when `CONTROL_PLANE_TOKEN` unset — this is intentional.
- OpenBB SDK has broken auto-generated package files — use REST API (:6900).
- Kimi CLI auth tokens expire ~1h — use HTTP API via inference-proxy (Moonshot or OpenRouter), not the CLI.
- macOS `python3` may resolve to brew 3.14 (no pytest) — use `/usr/local/bin/python3`.
- GPU Ollama needs `OLLAMA_HOST=0.0.0.0` after Windows reboot.
- Windows Ollama `/v1/` returns empty — proxy uses native `/api/chat`.
- Event bus silently degrades to JSONL if Redis is down — check `tail -f data/events/bus.jsonl` if you expect Redis events.
- x402 is gated by `X402_ENABLED=1`; without a recipient addr, requests pass through unpaywalled.
- Position sizing unknown-stage = 0 (paper). If an order is unexpectedly zero-sized, check `execution_stage` for typos.
- Prediction scoring is timeframe-aware — a 24h forecast written at 12:00 won't score until 12:00 next day.
- Windows SSH user is `aribs`, not `aspec`.
- cyber-threat-bot: `PYTHONPATH=src python3 -m cyber_threat_bot ...` (editable install unreliable).

## Authoritative Docs

- `docs/architecture-overview.md` — module wiring diagram
- `docs/opus-audit-2026-04-17.md` — security review (source of current hardening)
- `docs/crypto-integrations-plan.md` — x402 + chain roadmap
- `docs/nist-alignment.md` — NIST CSF control map
- `docs/QUICK_START_GUIDE.md` — first-run setup
- `docs/LOGGING.md` — event + audit log schema
- `docs/CLOUDFLARE_DNS_SETUP.md` — tunnel config
- `docs/setup/WINDOWS_*.md` — Windows node bringup
- `docs/setup/PI_ETHERNET_BRIDGE_SETUP.md` — Pi networking
