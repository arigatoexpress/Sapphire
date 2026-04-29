# Sapphire OS

Autonomous trading + intelligence + content ops. Telegram-first, agent-driven, event-bus mediated. Python 3.11+.

## Commands

```bash
# Test
pytest tests/unit/ --tb=short -q           # 5,740 collected by test_inventory.py
pytest plugins/claw-sapphire/tests/ -q     # 490 collected by test_inventory.py

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

# Makefile shortcuts (see `make help`)
make test          # core unit tests
make test-all      # core + plugin
make lint          # ruff check
make fix           # ruff --fix + format
make doctor        # scripts/ops/doctor.sh — environment health check
make registry      # validate infra/tool-registry.yaml invariants
make ci            # mirror GitHub Actions CI locally
```

## Dev Environment

- **Lint + format:** `ruff` only (see `[tool.ruff]` in `pyproject.toml`). Black/isort/flake8 were retired 2026-04-19. Pre-existing stylistic rules (E701, E722, E741, SIM102/105, B007, F811) are *track-only ignores* — new code is kept clean by the PostToolUse hook in `.claude/settings.json`.
- **Pre-commit:** `ruff + ruff-format + gitleaks + bandit + stdlib hooks`. Install with `make install-hooks`.
- **CI:** `.github/workflows/ci.yml` runs ruff + pytest (core + plugin) + `validate_tool_registry.py` + gitleaks on every push and PR. `security.yml` runs osv-scanner, trivy-fs, and bandit daily.
- **Dependabot:** pip + github-actions weekly (`.github/dependabot.yml`). Ruff and pytest grouped.
- **CODEOWNERS:** review-gated paths: `.github/`, `lib/security/`, `lib/core/kill_switch.py`, `contracts/`, `services/webhook/`, trading critical path.
- **PR/issue templates:** `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/{bug,feature}.md`.
- **Agent hooks:** `.claude/settings.json` blocks edits to `*secrets*`, `*.env`, `*trading_signals*`, `*migrated_customers*`; auto-runs `ruff format --fix` and `pytest tests/test_<basename>.py` after every Edit/Write.

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

**Key counts (verified 2026-04-29 after `/showcase`):** 6,294 collected tests (5,804 core + 490 plugin, per `scripts/ops/test_inventory.py --check-readme`) · 43 dashboard pages · 7 quant strategies · 20 LaunchAgents (folded in by the 2026-04-21 audit; see `docs/archive/2026/audits/launchagents-audit-2026-04-21.md`) · 21 scheduled tasks · 2 smart contracts.

| Path | Type | Description |
|------|------|-------------|
| `lib/core/` | library | Risk kernel, position sizing, **event_bus**, **heartbeat** (60s state machine), **kill_switch** (global + security), **confirmation_firewall** (2-phase commit), **decision_engine** (explainable autonomous ranking), **security_monitor**. Also `src/sapphire_core/` package (cognitive agent, executor, gateway, memory, telegram_bot). |
| `lib/analytics/` | library | 24 modules — strategies (7: RegimeAwareRSI, FundingRateContrarian, CorrelationBreakout, MultiTFMomentum, SapphireComposite + base + params), CPCV, regime GMM, VPIN, backtest_engine, risk_engine, deflated_sharpe, liquidation, correlation, factors, forecast (Kronos+TA consensus), performance, performance_tracker, prediction_accuracy, brain_accuracy, strategy_performance, backtest_results, signal_enhancer, self_optimizer, run_strategies, sentiment, indicators. |
| `lib/chain/` | library | On-chain intelligence: regime, funding, OI, TVL, stablecoin supply, whale flow. **`coinmetrics.py`** (on-chain fundamentals), **`robinhood_chain.py`** (Arbitrum Orbit chain ID 46630 web3 client), `intelligence.py`, `sources.py`, `providers/` (CoinGlass, Dune, Whale Alert, Santiment, CoinAPI, BGGeometrics). |
| `lib/content/` | library | 14-module research-to-publish pipeline: `data_collector` → `thesis_engine` → `draft_generator` → `report_generator` → `visualizations` → `quality` (7-check rubric) → `performance_policy` (blocks premature accuracy claims) → `qa_pipeline` → `formatters` → `approval` (Telegram sign-off) → `publisher`/`auto_publish` → `scheduler` (Mon brief / Wed AI intel / Fri security / daily pulse). Publishers: `substack`, `x`, `linkedin`, `typefully`. Also `outreach.py` (lead-engine integration). |
| `lib/foundry/` | library | **Palantir Foundry integration**: `client` (bearer + OAuth), `ingestion` (local → ontology objects), `readiness` (repo-grounded audit), `sync` (15-min delta-aware + Telegram alerts). |
| `lib/portfolio/` | library | **`robinhood.py`** — Robinhood Crypto API client (Ed25519-signed REST, accounts, holdings, best_bid_ask, order history, reconstructed cost basis). Credentials in `~/.config/sapphire-secrets/`. |
| `lib/security/` | library | **Security platform**: `dependency_scanner` (OSV.dev CVE lookup + CycloneDX 1.5 SBOM), `model_monitor` (Ollama blob SHA-256 + Jinja2 backdoor detection), `network_mapper` (Tailscale topology + trust-zone scoring + attack-surface). |
| `lib/intel/` | library | `market_intelligence.py`, `lead_enricher.py`. |
| `lib/payments/` | library | `x402_middleware.py` — HTTP 402 micropayment gate (Flask + raw-socket), EVM signature verification. |
| `lib/agents/` | library | Paper-only autonomous harness (`base.py`, `alpha_agent.py`, `runner.py`) plus the broader OpenClaw/NemoClaw dispatch stack under `src/sapphire_agents/`. |
| `lib/telegram/` | library | `kimi_relay.py`, `login_widget.py` (HMAC-SHA256 Login Widget verifier). |
| `lib/trading/` | library | `solana_wallet.py`. |
| `services/alpha/` | service | Trading engine + signal logger [Mac:18081]. |
| `services/analytics_dashboard/` | service | Analytics-focused dashboard variant. |
| `services/aster/` | service | Aster DEX bot — Solana perps (paused). |
| `services/control-plane/` | service | PM hub: projects, tasks, events, Kimi bridge [Mac:8082]. |
| `services/dashboard/` | service | Flask dashboard [Mac:8080] — 43 pages including the unified `/showcase`, SSE event stream, performance + forecast + backtest endpoints. |
| `services/foundry_sync/` | service | Scheduled Foundry sync daemon — wraps `lib/foundry/sync.py`. |
| `services/heartbeat/` | service | Heartbeat daemon wrapper (`run.py`, `heartbeat.py`). |
| `services/hyperliquid/` | service | Hyperliquid L1 bot — public-feed signal subscriber + live-trading executor (`hyperliquid_bot/risk.py`, hard caps: $5/order, 3x lev, 5 positions, $25/day loss, file-killswitch). Mainnet refused until EIP-712 signing is verified on testnet (`policy.signing_verified=False`). |
| `services/inference-proxy/` | service | 4-tier LLM failover [Mac:11435] + x402 gate. |
| `services/intelligence/` | service | Daily brief generator, chain refresh. |
| `services/pipeline/` | service | GCP sync — events → GCS + BigQuery (hourly watermark). |
| `services/scout-sandbox/` | service | External-collaborator least-privilege sandbox. |
| `services/security_pipeline/` | service | Scheduled full-system security scan → SOC page. |
| `services/telegram-bot/` | service | Legacy bot (replaced by hermes-agent gateway). |
| `services/webhook/` | service | TradingView webhook receiver [Windows:9090]. |
| `plugins/claw-sapphire/` | plugin | 63 tool scripts on disk (36 at top level + 25 in `internal/` + 2 in `_deprecated/`), 10 libs, 376 collected tests. |
| `contracts/` | solidity | **`SapphireSignalVerifier.sol`** (on-chain signal registry with ZK proof hash field), **`SapphirePaymentGate.sol`** (micropayment gate). Deployed on Robinhood Chain testnet via `scripts/deploy_robinhood_chain.py`. |
| `pine/` | pine | 5 TradingView strategies (standalone/: v1, v2, v3 Ultra, MultiSymbol Screener, Mac variant). |
| `skills/` | skills | Agent-executable capabilities. |
| `data/content/` | data | Content engine drafts + ready/ queue. |
| `data/chain/` | data | Deployed contract addresses (`deployments.json`), chain snapshots. |
| `data/benchmarks/kadima-labs/` | data | Kadima Labs AI benchmark (v1–v3). |
| `infra/launchagents/` | infra | 20 macOS LaunchAgent plists (folded in by the 2026-04-21 audit: chain-refresh, control-plane, correlation-refresh, daily-brief, gcp-sync, logrotate, openbb-api, signal-logger, telemetry-collector, threat-refresh) plus 1 disabled template. |
| `infra/agent-manifest.yaml` | infra | Lean 5-tool subset the LLM sees. |
| `infra/tool-registry.yaml` | infra | Full plugin tool registry (CI-enforced by `scripts/validate_tool_registry.py`). |
| `infra/tailscale-acl.json` | infra | Tailscale mesh ACL. |
| `infra/setup-sops.sh` | infra | SOPS / age bootstrap. |

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

## Sapphire Plugin (63 tools on disk, 15 registered in plugin.json)

`plugins/claw-sapphire/plugin.json` declares 15 Claude Code tools (one `sapphire` namespace entry + 14 `sapphire_*` tools, for 16 entries total): `dispatch`, `verify`, `budget`, `state`, `status`, `notify`, `health_check`, `market`, `predict_kronos`, `threat_intel`, `lumo_research`, `starred_repos`, `macro_data`, `lead_engine`, `trading_brain`. The remaining tool scripts are standalone, invoked via stdin JSON by hermes skills, scheduled tasks, dashboards, or other tools.

```
plugins/claw-sapphire/tools/
├── <name>.py               registered  (36 top-level files, agent-facing)
├── internal/<name>.py      internal    (25, invoked by scheduled tasks / hermes / services)
└── _deprecated/<name>.py   deprecated  (2, in sunset window)
```

Tool groups:
- **Intel / analytics (6):** `vote_monitor`, `watchdog`, `digest`, `research`, `events`, `qa_aware_factory`
- **Trading (8):** `predict` (6-factor TA, **verified 61.1% overall, BTC 83.3%, ETH 50.0%, SOL 50.0% on 36 scored of 42 predictions**), `signal_generator`, `paper_trader`, `crypto_portfolio`, `backtest`, `macro_data` (graceful error when FRED key is missing), `trading_brain`, `market_sentiment`
- **Other (5 + 1 legacy alias):** `lead_engine`, `lead_enrich`, `lumo`, `tho_intel`, `solana_wallet`, `kronos_predict` (legacy wrapper — prefer `predict_kronos`)

**Agent manifest** (`infra/agent-manifest.yaml`) — the lean 5-tool subset the LLM actually sees: `sapphire_market`, `sapphire_dispatch`, `sapphire_notify`, `sapphire_verify`, `sapphire_state`.

**Invariants (CI-enforced by `scripts/validate_tool_registry.py`, run by `sapphire-ci-monitor`):**
1. Every `.py` under `tools/` (excluding `__init__.py`) is listed in the registry (`infra/tool-registry.yaml`).
2. Every registered tool's file exists and parses.
3. Every deprecated entry has a shim that calls `warnings.warn(..., DeprecationWarning)`.
4. `agent-manifest.yaml` is a strict subset of registry entries with `status: registered` and `agent_facing: true`.

`plugins/claw-sapphire/lib/` — 10 shared modules:
- `technical_analysis.py` — RSI, MACD, Bollinger, MA, ATR, volume (from OpenBB OHLCV)
- `nemotron.py` — Ollama client with failover (proxy → GPU → Mac)
- `quant_analysis.py` — S/R detection, correlation, trend strength
- `router.py`, `runtime_policy.py`, `token_governor.py` — dispatch policy + budget
- `sensitivity_classifier.py` — PII/secret regex (used by dispatch, not proxy)
- `market_data.py`, `nvidia_agents.py` — shared market + NeMo helpers

## Inference Proxy (`services/inference-proxy/`)

4-tier failover (threaded server — concurrent requests safe). hermes-agent and all plugin tools talk to this.
- **T1 Windows GPU** (100.71.10.48:11434): native `/api/chat` (NOT `/v1/` — returns empty on Windows). ~0.4s.
- **T2 Pi rari1** (100.120.191.1:11434): nemotron-mini, smollm2, qwen2.5:0.5b, gemma2:2b. `PI_RARI1_ENABLED=1`. T2 routing should downshift to the smaller Pi-safe models for live traffic instead of trying `nemotron-mini:latest`.
- **T2 Pi rari2** (100.87.225.89:11434): ONLINE as of 2026-04-18 (5 models). `PI_RARI2_ENABLED=1`.
- **T3 Mac local** (127.0.0.1:11434): `/v1/chat/completions` passthrough. ~90s (CPU inference).
- **T4 Kimi Cloud** (api.moonshot.cn): non-sensitive only. `MOONSHOT_API_KEY` loaded from `~/.sapphire/secrets.env` (mode 0600, not in plist).
- Model aliases: `fast`/`quick`→nemotron-mini:latest, `auto`/`balanced`→hermes3:8b, `deep`→qwen3:14b, `code`→gemma4:latest, `reason`→deepseek-r1:14b, `qwen-reason`→qwen3.5:9b, `qwen3.6`→qwen3.6:27b (Windows primary, Mac exact fallback, explicit only), `cascade`/`moe`→nemotron-cascade-2, `large`→qwen2.5:32b, `kimi`→kimi-cloud
- GPU-only models (>8B params): Windows only, 503 if GPU down
- Sensitivity gate: regex blocks api_key/password/jwt/SSN/CC from T4
- Health: 60s cooldown, background 30s probe, `/metrics` endpoint
- Endpoints: `/health`, `/metrics`, `/v1/chat/completions`, `/v1/models`

## Trading Pipeline

TradingView → webhook (Win :9090) → signal logger (Mac :18081) → Telegram
Autonomous signal generator scans RSI/MACD/BB/MA → generates signals → paper trades
Paper portfolio: $100K, ATR-based SL/TP (1.67:1 R:R), 10% position sizing
Prediction accuracy: 61.1% overall, BTC 83.3% (n=36 scored of 42)

**Hyperliquid live executor (`services/hyperliquid/src/hyperliquid_bot/risk.py`):**
- Caps: `$5/order`, `3x` max leverage, `5` max open positions, `$25/day` realized-loss auto-pause.
- Killswitch: `~/.sapphire/hyperliquid_trading_pause` (drop file → blocks every order, mirrors routine-pause from #392).
- Gates: `HYPERLIQUID_TRADING_ENABLED=0` (default → all orders dry-run-logged), `HYPERLIQUID_TESTNET=1` (default → testnet).
- Key: macOS keychain `security -a sapphire-hyperliquid -s sapphire -w` first, env `HYPERLIQUID_PRIVATE_KEY` fallback.
- Mainnet refused until `HyperliquidLivePolicy.signing_verified=True`. Signing now follows the canonical Hyperliquid scheme (`hyperliquid_bot/signing.py`: msgpack(action) || nonce || vault || expiry → keccak256 → phantom Agent → EIP-712 typed-data, domain `Exchange/1/1337/0x0…0`, mainnet/testnet encoded in `source` `"a"`/`"b"`). Verify with `python3 scripts/ops/verify_hyperliquid_signing.py [--info | --testnet-order]` before flipping the policy field.
- Audit: every `execute_signal` appends to `data/hyperliquid_trades.jsonl`; daily realized loss tally at `data/hyperliquid_daily_pnl.json`.
- Read-only status: `echo '{"action":"live-status"}' | python3 plugins/claw-sapphire/tools/hyperliquid.py`.

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

Tests at `tests/unit/test_strategy_performance.py`, `test_backtest_results.py`, `test_forecast.py` (57 tests). To regenerate a backtest sweep: `python3 -m lib.analytics.run_strategies --days 90` — runs in ~2s and produces a fresh `strategy_sweep_*.json` + `best_per_symbol_*.json` under `data/backtests/strategies/`. The previous "signature-drift bug" note was stale: `Backtester.__init__` accepts both `(cfg)` and `(bankroll, fee_bps)` since PR #98, and the actual Apr-21 zero-trade regression was a unit-mismatch in `BacktestEngine.run` that emitted percent-scaled `total_return_pct`/`win_rate`/`max_drawdown_pct` against a fraction-scale dashboard contract — fixed by dividing by 100 in the `SimpleNamespace` projection.

## Cloud Routines (claude.ai/code/routines) — 8

These run on Anthropic infrastructure on cron, regardless of whether Claude Code is open or the Mac is online. Each is driven by a runbook in `docs/ops/<name>-runbook.md` and produces a single GitHub-side-effect (issue or draft PR). Manage via the `RemoteTrigger` MCP tool (`list`, `get`, `create`, `update`, `run`) or the `claude.ai/code/routines` UI.

| Routine | Cron (UTC) | Runbook | Side effect |
|---|---|---|---|
| Sapphire mission status digest | `0 14 * * 1` | `mission-status-digest-runbook.md` | Mon issue, label `mission-digest` |
| Sapphire content-engine soak collector | `0 13 * * *` | `content-engine-soak-runbook.md` | Daily PR if drift |
| Sapphire factory test guardian | `0 4 * * *` | `factory-test-guardian-runbook.md` | Issue per test-failure fingerprint |
| Sapphire factory repo fixer | `0 5 * * *` | `factory-repo-fixer-runbook.md` | Daily draft PR if ruff fixed anything |
| Sapphire dependency drift digest | `0 12 * * 3` | `dependency-drift-digest-runbook.md` | Weekly digest issue |
| Sapphire threat intel sweep | `0 11 * * *` | `threat-intel-sweep-runbook.md` | Issue per new-CVE fingerprint |
| Sapphire github discovery | `0 13 * * 1` | `github-discovery-runbook.md` | Weekly digest issue |
| Sapphire evening digest | `0 0 * * *` | `evening-digest-runbook.md` | Daily issue |

All 8 are read-only or PR/issue-only (no auto-merge, no live trading, no secrets in body, restricted-path fences on the only fixer). The pattern: cloud routine prompt instructs the agent to read its runbook and execute it exactly — runbook is the full task spec.

**Soak window**: cloud routines launched 2026-04-27. Local mirrors of the 5 last cloud routines (factory-test-guardian, factory-repo-fixer, threat-intel-sweep, github-discovery, evening-digest) stay live until ~2026-05-11; retire then only with evidence the cloud equivalents produce clean signals.

## 22 Scheduled Tasks (Claude Code)

All in `~/.claude/scheduled-tasks/`. Run when Claude Code is open. Tasks marked `[CLOUD]` have a cloud-routine equivalent firing on Anthropic infra; both run during the soak window.
- sapphire-morning-briefing (8 AM) — 6-section digest → Telegram
- trading-research (5:42 AM) — TA predictions + scoring
- market-pulse (8/12/4 M-F) — signal scan + paper trade stops
- threat-intel-sweep (6:30 AM + 2 PM) — CISA/NVD `[CLOUD]`
- github-discovery (7 AM) — star sync + trending `[CLOUD]`
- tho-production-healthcheck (*/2h) — watchdog
- tho-test-writer (11 AM + 11 PM) — coverage growth (now opens draft PR)
- creative-experimenter (2 AM) — nightly R&D
- factory-test-guardian (3 AM + 3 PM) — all test suites `[CLOUD]`
- factory-repo-fixer (*/6h) — auto-fix lint via branch + draft PR (no longer pushes to main directly) `[CLOUD]`
- code-quality-sweep (1 PM) — dead code, imports
- evening-digest (6 PM) — daily summary `[CLOUD]`
- sapphire-self-improvement (8:53 PM) — priorities
- sapphire-ci-monitor (*/3h) — lint + tests
- factory-client-delivery (10 AM M-F) — THO production
- vote-monitor-collector (*/4h) — DeFi pool snapshots; uses regional-intel `/api/health` + `digest`
- dependency-security-scan (Wed 4 AM) — vuln + secrets
- sapphire-weekly-review (Sun 9 AM) — architecture audit
- backtest-sweep (weekly) — full strategy backtest sweep
- lead-generation (daily) — paste-safe summary only (Telegram send removed)
- scheduled-task-health-monitor (daily 9 AM) — meta: lists tasks via MCP, opens issue if any task is >2× its expected interval stale
- pull-gcp-secrets — `[RETIRED 2026-04-27]` (one-shot fired 2026-04-02)

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
- `docs/crypto-integrations-plan.md` — x402 + chain roadmap (Robinhood Chain appended 2026-04-19)
- `docs/nist-alignment.md` — NIST CSF control map
- `docs/foundry-strategy-2026-04-19.md` — Palantir Foundry value thesis + integration plan
- `docs/foundry-ontology-schema.md` — Foundry ontology object schema
- `docs/palantir-foundry-strategy-2026-04-19.md` — Partnership-facing Foundry strategy
- `docs/gcp-data-engineering.md` — Data lake design, BigQuery schema
- `docs/kronos-integration-plan.md` — Kronos ML forecasting
- `docs/tradingview-cdp-setup.md` — TradingView CDP setup
- `docs/QUICK_START_GUIDE.md` — first-run setup
- `docs/LOGGING.md` — event + audit log schema
- `docs/CLOUDFLARE_DNS_SETUP.md` — tunnel config
- `docs/setup/WINDOWS_*.md` — Windows node bringup
- `docs/setup/PI_ETHERNET_BRIDGE_SETUP.md` — Pi networking
