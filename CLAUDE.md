# Sapphire OS

Autonomous trading + intelligence + content ops. Telegram-first, agent-driven, event-bus mediated. Python 3.11+.

## Commands

```bash
# Test
pytest tests/unit/ --tb=short -q           # 1,251 tests (use /usr/local/bin/python3 on Mac)
pytest plugins/claw-sapphire/tests/ -q     # 13 plugin tests

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

Event bus: Redis Streams primary → SQLite local-bus fallback (survives Redis outage, rehydrates on reconnect).

## Module Map

| Path | Type | Description |
|------|------|-------------|
| `lib/core/` | library | Risk kernel, circuit breaker, position sizing, models, logging, pubsub, **event_bus** |
| `lib/payments/` | library | **x402 HTTP 402 micropayment middleware** (Flask + raw-socket gates, EVM signatures) |
| `lib/chain/` | library | **On-chain intelligence**: regime, funding, OI, TVL, stablecoin supply, whale flow |
| `lib/content/` | library | **Content engine**: weekly report generator, outreach, quality gate, publisher |
| `lib/analytics/` | library | Correlation engine, risk/exposure analytics |
| `lib/agents/` | library | OpenClaw/NemoClaw dispatch, orchestrator, runtime policy, token governor |
| `lib/telegram/` | library | Telegram bot framework + handlers |
| `services/alpha/` | service | Trading engine + signal logger [Mac:18081] |
| `services/aster/` | service | Aster DEX bot — Solana perps (paused) |
| `services/hyperliquid/` | service | Hyperliquid L1 bot (stub) |
| `services/dashboard/` | service | Flask dashboard [Mac:8080, auth:sapphire] — SSE event stream, content page, metrics |
| `services/control-plane/` | service | PM hub: projects, tasks, events, Kimi bridge [Mac:8082] |
| `services/inference-proxy/` | service | 4-tier LLM failover [Mac:11435] + **x402 gate** |
| `services/pipeline/` | service | GCP sync stub — syncs events → GCS/BigQuery (`gcp_sync.py` only, not a daemon) |
| `services/scout-sandbox/` | service | External-collaborator least-privilege sandbox |
| `services/webhook/` | service | TradingView webhook receiver [Windows:9090] |
| `services/telegram-bot/` | service | Legacy bot (replaced by hermes-agent gateway) |
| `plugins/claw-sapphire/` | plugin | Claw-code plugin: 27 tools + lib + 25 tests |
| `pine/` | pine | TradingView strategies (v1-v3 Ultra, 80%+ win rate target) |
| `skills/` | skills | Agent-executable capabilities |
| `data/content/` | data | Content engine drafts + ready/ queue |
| `data/benchmarks/kadima-labs/` | data | Kadima Labs AI benchmark (v1-v3) |
| `infra/launchagents/` | infra | macOS LaunchAgent plists (incl. content-engine) |

## Event Bus

`lib/core/event_bus.py` — central nervous system.

- **Redis Streams** primary transport when `REDIS_URL` is set (XADD/XREAD with consumer groups).
- **SQLite local bus** fallback (`data/event_bus.sqlite`) — survives Redis outage, buffers events, rehydrates.
- Publishers: `signal_pipeline`, `correlation`, `threat_intel`, `chain/intelligence` (failures never break the producer).
- Subscribers: dashboard SSE (`/api/events/stream?types=signal.*,threat.*`), content engine, Telegram dispatcher.
- **Replay**: `GET /api/events/replay?type=signal.generated&limit=100` replays historical events.
- **World state**: `GET /api/events/world-state` returns aggregated current snapshot.

Event types in active use: `signal.generated`, `signal.closed`, `correlation.broken`, `threat.detected`, `chain.regime.shift`, `chain.funding.skew`.

## x402 Payment Gate

`lib/payments/x402_middleware.py` — HTTP 402 micropayments (Base/Solana).

- Disabled by default — set `X402_ENABLED=1` + `X402_RECIPIENT=<evm_addr>` to activate.
- Request without `X-PAYMENT` header → `402 Payment Required` with `accepts` manifest (amount, asset, chain, recipient).
- Client signs EIP-712 permit → retries with header → middleware verifies signature + replay protection → forwards.
- Priced surfaces: `/v1/chat/completions` ($0.001), `/v1/completions` ($0.001), `/v1/embeddings` ($0.0005), dashboard `/api/chain/overview` ($0.01), `/api/risk/metrics` ($0.02), `/api/kronos_prediction` ($0.05). Override via `X402_PRICE_*` env vars.
- `_ReplayCache` bounded LRU on payment-ID hash — single-use payments only.

## Content Engine

`lib/content/` — weekly intelligence report generator.

- `report_generator.py` — consumes events (`signal.closed`, `threat.detected`, `chain.regime.shift`) + paper_trader journal → markdown report.
- `quality.py` — rule-based gate (no empty sections, min-count per section, factual-claim style check).
- `formatters.py` — markdown/HTML/Telegram long-form formatters.
- `publisher.py` — moves drafts `data/content/drafts/` → `data/content/ready/` after quality pass.
- `scheduler.py` — weekly cadence, consumed by `infra/launchagents/com.sapphire.content-engine.plist`.
- `outreach.py` — lead-engine handoff (report → targeted outreach draft).
- Dashboard surface: `/content` (gated) lists latest drafts from `/api/content/drafts`.

## On-Chain Intelligence

`lib/chain/intelligence.py` — 560-line orchestrator, consumed by dashboard `/api/chain/overview`.

Signals (all cached with short TTLs to stay cheap):
- **Regime** — BTC/ETH realized vol + trend slope → `bull/bear/chop`
- **Funding skew** — perp funding rate across venues, z-scored vs. 30-day median
- **OI delta** — open interest MoM change, filtered for short squeeze/long flush conditions
- **TVL shift** — DefiLlama total/per-protocol deltas
- **Stablecoin supply** — USDC/USDT circulating supply flow (risk-on/risk-off proxy)
- **Whale flow** — large-transfer stream from chain RPCs
- Emits `chain.regime.shift` on state change (not every poll) — downstream consumers debounce.

## Inference Proxy (localhost:11435)

4-tier failover; hermes-agent and plugin tools all route through this.

- **T1 Windows GPU** (100.71.10.48:11434): native `/api/chat` (NOT `/v1/` — empty on Windows)
- **T2 Pi rari1/rari2** (100.120.191.1 / 100.87.225.89): lightweight models only (≤4B), `PI_OLLAMA_ENABLED=1`
- **T3 Mac local** (127.0.0.1:11434): `/v1/chat/completions` passthrough
- **T4 Kimi Cloud** (api.moonshot.cn / OpenRouter): `MOONSHOT_API_KEY` or `OPENROUTER_API_KEY` — non-sensitive only
- Model tiers: `fast`→nemotron-mini, `balanced`→hermes3:8b, `deep`→qwen3:14b, `code`→qwen2.5-coder:14b, `reason`→deepseek-r1:14b, `large`→qwen2.5:32b, `kimi`→kimi-k2.5
- **Sensitivity gate**: multi-group regex classifier (auth/secrets, financial PII, system internals, wallet addrs) blocks Kimi routing. Over-matches are safe (stay local).
- **Health**: per-endpoint 60s cooldown, module-level lock protects the health + metrics dicts (ThreadingHTTPServer-safe).
- **Body limit**: 4 MB hard cap.
- **x402**: optional paywall on `/v1/*` endpoints (see above).

## Trading Pipeline

```
TradingView Desktop / Pine
        │ (webhook)
        ▼
webhook:9090 (Win)  →  signal_logger:18081 (Mac)
                              │
                              ▼
                      signal_pipeline (kernel + Kelly + ATR stops)
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
        event_bus         paper_trader      Telegram
      signal.generated    ($100K book)      (priority)
```

- Paper portfolio: $100K notional, ATR-based SL/TP (1.67:1 R:R), 10% position sizing baseline scaled by Kelly.
- **Stage multiplier fails closed to 0.0** for unknown stages — a typo in `execution_stage` no longer promotes a paper order to full_live.
- Prediction accuracy: 58% overall, BTC 75% (rolling 30-day).
- Scoring respects timeframe: `action_score()` only marks a 24h forecast once 24h elapsed (prior bug scored instantly → meaningless stats).

## Security Posture

- Dashboard Basic Auth uses `secrets.compare_digest` (no timing leak).
- Control plane fails closed when `CONTROL_PLANE_TOKEN` unset (was silent open-relay before).
- Inference-proxy sensitivity gate is *enabled* (was dead code); patterns cover API keys, private keys, EVM/Solana addrs, Tailscale CGNAT IPs.
- Position sizing unknown-stage → 0.0 (never 1.0).
- Notify (Telegram) keeps SSL verification on — no CERT_NONE fallback.
- See `docs/opus-audit-2026-04-17.md` for the security review that produced these fixes.

## Infrastructure

**Mac (100.67.171.79) — commander, all services:**
- control-plane:8082, dashboard:8080, signal-logger:18081
- inference-proxy:11435 (4-tier failover)
- hermes-agent gateway (ai.hermes.gateway LaunchAgent, Telegram bot)
- content-engine (com.sapphire.content-engine LaunchAgent, weekly cadence)
- OpenBB:6900, Redis:6379, Ollama:11434

**Windows (100.71.10.48) — GPU + services:**
- Ollama:11434 (26 models, RTX 5070 Ti 16GB VRAM, `OLLAMA_HOST=0.0.0.0`)
- webhook:9090 (TradingView → Mac signal logger)
- telemetry-dashboard:3001 (React + WebSocket)
- SSH: `ssh aribs@100.71.10.48` (ed25519)

**Pi rari1 (100.120.191.1)** — ethernet, online; Ollama optional (`PI_OLLAMA_ENABLED=1`).
**Pi rari2 (100.87.225.89)** — ethernet, online; signal-logger:18081 active.

## Sapphire Plugin (27 tools)

`plugins/claw-sapphire/tools/` — all invoked via stdin JSON:

**Infra / ops**: `dispatch`, `verify`, `budget`, `state`, `status`, `notify`, `health_check`, `watchdog`, `events`

**Market / trading**: `market`, `predict`, `kronos_predict`, `signal_generator`, `paper_trader`, `backtest`, `crypto_portfolio`, `trading_brain`, `market_sentiment`, `macro_data`

**Intelligence**: `threat_intel`, `starred_repos`, `vote_monitor`, `tho_intel`, `research`, `digest`, `qa_aware_factory`

**Outreach**: `lead_engine`

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

## Event System (JSONL + bus)

Two parallel streams:
- **JSONL audit log** (`data/system_events.jsonl`) — append-only, machine-grepable. Tags: `project:` `agent:` `priority:` `type:` `service:` `device:`. Persists even if event_bus is down.
- **event_bus** — live delivery to subscribers (see above).

Registries: `data/connectors.json`, `data/device_topology.json`.

## 20 Scheduled Tasks (Claude Code, `~/.claude/scheduled-tasks/`)

- morning-briefing (8 AM) — 6-section digest
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
- Event bus silently degrades to SQLite if Redis is down — check `tail -f data/event_bus.sqlite-wal` if you expect Redis events.
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
