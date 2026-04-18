# Sapphire OS — Architecture Overview

High-level system map for Sapphire — an autonomous trading + project-management + intelligence stack built around a Telegram heartbeat and an agent-driven runtime.

## 1. System Shape

```
                            ┌─────────────────────┐
                            │  Human operator     │
                            │  (Telegram)         │
                            └──────────┬──────────┘
                                       │ /focus /steer /autonomy
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              ▼                              │
        │              ┌─────────────────────────────┐                │
        │              │  hermes-agent gateway       │                │
        │              │  (NousResearch, polling)    │                │
        │              │  ai.hermes.gateway          │                │
        │              └──────────┬──────────────────┘                │
        │                         │ OpenAI-compat                     │
        │                         ▼                                   │
        │        ┌───────────────────────────────────────┐            │
        │        │  inference-proxy  (Mac :11435)        │            │
        │        │  ─────────────────────────────────    │            │
        │        │   T1  Windows GPU  /api/chat  │RTX    │            │
        │        │   T2  Pi rari2     ≤4B models │ethernet│           │
        │        │   T3  Mac Ollama   /v1/chat            │           │
        │        │   T4  Moonshot / OpenRouter / Kimi     │           │
        │        │       Claw Telegram relay   (sensitive │           │
        │        │       content blocked at classifier)   │           │
        │        └───────────────────────────────────────┘            │
        │                         ▲   ▲                               │
        │  ┌──────────────────────┘   └────────────────────────┐      │
        │  │                                                   │      │
        │  ▼                                                   ▼      │
  ┌──────────────┐   ┌─────────────────────┐     ┌──────────────────┐ │
  │ plugin       │   │ services/alpha      │     │ services/        │ │
  │ claw-sapphire│   │ (trading engine,    │     │ control-plane    │ │
  │ (26 tools)   │   │  uvloop, 150KB      │     │ (PM hub :8082)   │ │
  │              │   │  main.py)           │     │ FastAPI + SQLite │ │
  └──────┬───────┘   └──────┬──────────────┘     └──────┬───────────┘ │
         │                  │                           │             │
         │                  │ Redis pub/sub             │             │
         │                  ▼                           │             │
         │        ┌───────────────────┐                 │             │
         │        │  Redis :6379      │◀────────────────┘             │
         │        │  (event bus)      │                               │
         │        └─────┬─────────────┘                               │
         │              │                                             │
         │              ▼                                             │
         │    ┌──────────────────────┐   ┌─────────────────────────┐  │
         │    │ services/aster       │   │ services/hyperliquid    │  │
         │    │ Solana perpetuals    │   │ L1 EIP-712 orders       │  │
         │    └──────────────────────┘   └─────────────────────────┘  │
         │                                                            │
         ▼                                                            │
  ┌────────────────────────────────────────────────────────────┐      │
  │  data/  (JSONL event log + runtime state)                  │      │
  │  system_events / trading_signals / trading_predictions /   │      │
  │  paper_portfolio / agentic_board / connectors / topology   │      │
  └─────────────────┬──────────────────────────────────────────┘      │
                    │                                                 │
                    ▼                                                 │
         ┌──────────────────────────┐                                 │
         │ services/pipeline        │───▶ BigQuery (tho-ai-agent.     │
         │ gcp_sync.py              │     sapphire.<table>)           │
         │ (NDJSON watermark)       │───▶ GCS sapphire-data-lake/raw/ │
         └──────────────────────────┘                                 │
                                                                      │
                                                                      │
  ┌────────────────────────────────────────────────────────────┐      │
  │  services/dashboard (Flask :8080)                          │◀─────┘
  │  20+ pages / 20+ APIs. Basic-auth. 10s cached fetchers.    │
  │  /architecture /intelligence /chain /risk /soc /signals    │
  └────────────────────────────────────────────────────────────┘

         ┌──────────────────────────────┐
  External│ TradingView  ─webhook→       │
  signals │ Windows :9090  ─HTTP→        │───▶ signal_logger :18081
          │ Mac (Cloudflare Tunnel)      │    (JSONL per day)
          └──────────────────────────────┘
```

## 2. Request Lifecycles

### 2.1 Telegram command → claw-code session

```
Telegram user ──▶ hermes gateway (polling)
                      │
                      ▼
       inference-proxy (tier failover)
                      │
           ┌──────────┴──────────┐
           │                     │
       Windows GPU           Mac Ollama    ── sensitive? ──▶ classifier
                                                                │
                                                           kimi blocked
                                                          (response via T1–T3)
```

Non-hermes ingress (`services/telegram-bot/app.py` on :8088) is a second Telegram surface that maps `/status /scan /fix /budget …` directly to claw-code subprocesses with the Sapphire plugin loaded.

### 2.2 Trading signal → execution

```
TradingView  → (Cloudflare Tunnel)  → Windows :9090 webhook
                                          │
                                          ▼  HMAC verify
                                    signal_logger  (Mac :18081)
                                          │
                                          ▼  write data/signals/YYYY-MM-DD.jsonl
                                    Redis pub/sub  (channel: trading-signals)
                                          │
            ┌─────────────────────────────┴─────────────────────────────┐
            ▼                                                           ▼
    services/alpha (risk kernel)                                  signal_generator
       │                                                          (autonomous TA)
       ▼
    execution/dispatcher ── aster  (Solana)
                        └── hyperliquid  (L1)
       │
       ▼
    portfolio tracker → control-plane event stream → Telegram notify
```

### 2.3 Prediction → scoring loop

```
trading-research (5:42 AM)
    └── predict.py "predict"   → data/trading_predictions.jsonl
                                         │
                                         ▼ 24h later
                           predict.py "score"    ── accuracy history
                                                   58% overall, BTC 75%
                                         │
                                         ▼
                             trading_brain.py "dashboard"
                             (ensemble: TA + signals + Kronos + macro
                              + track record → GO_LONG / WAIT)
                                         │
                                         ▼
                              paper_trader (ATR stops, 1.67:1 R:R)
```

### 2.4 Data lake push

```
Local JSONL (data/*.jsonl)  ──▶  services/pipeline/gcp_sync.py
                                           │
           ┌───────────────────────────────┴───────────────────────────────┐
           │ 1. read watermark                                             │
           │ 2. transform rows (infra/gcp/schemas/*.json)                  │
           │ 3. upload gs://sapphire-data-lake/raw/<source>/YYYY-MM-DD/    │
           │ 4. BQ load → tho-ai-agent.sapphire.<source>                   │
           │ 5. advance watermark                                          │
           └───────────────────────────────────────────────────────────────┘
```

## 3. Components

### Services (10)

| Service | Runtime | Port | Purpose |
|---------|---------|------|---------|
| alpha | uvloop | — | Trading engine: signals, risk kernel, execution, self-improvement. `src/main.py` orchestrates; `src/signal_logger.py` exposes :18081. |
| aster | async Python | — | Aster DEX (Solana) perpetuals bot. Shield HFT strategy. |
| control-plane | FastAPI | 8082 | PM hub. Projects, tasks, JSONL event stream, Kimi dispatch bridge, runtime policy. |
| dashboard | Flask | 8080 | Ops surface. 20+ pages, 20+ APIs. Basic-auth. |
| hyperliquid | async Python | — | Hyperliquid L1 perps. EIP-712 signed. |
| inference-proxy | stdlib http.server | 11435 | 4-tier LLM failover, OpenAI-compatible. |
| pipeline | CLI | — | GCP data-lake sync (BigQuery + GCS). |
| scout-sandbox | Python | — | GTM outbound + web-intel broker. Env-guarded. |
| telegram-bot | FastAPI | 8088 | Thin claw-code webhook (NemotronRariBot). |
| webhook (Windows) | — | 9090 | TradingView → HMAC-verified → signal_logger. |

### Libraries

- **lib/core/src/sapphire_core/** — risk kernel, circuit breaker, position sizing, models, pub/sub clients, logging, health, cognitive mesh, episodic memory, error classifier, confirmation firewall, execution idempotency, symbol resolver, neural cache, smart notifications.
- **lib/agents/src/sapphire_agents/** — orchestrator (master), OpenClaw/NemoClaw dispatch, runtime policy whitelist, token governor.
- **lib/analytics/** — correlation matrix, risk engine.
- **lib/telegram/src/sapphire_telegram/** — bot + command handlers.

### Plugin (`plugins/claw-sapphire/`)

26 tools grouped into routing/runtime, market/signals, research/intel, ops. 9 libraries. 2 hooks. See CLAUDE.md for the full table.

### Scheduled routines (20)

Run when Claude Code is open; all under `~/.claude/scheduled-tasks/<name>/SKILL.md`. Morning briefing (8 AM) and evening digest (6 PM) bookend the day. Trading loop: trading-research (5:42) → market-pulse (every 4h) → self-improvement (8:53 PM).

## 4. Data Stores

| Store | Purpose | Location |
|-------|---------|----------|
| Redis | Event bus (pub/sub). `lib/core/pubsub/redis_client.py` | Mac :6379 |
| JSONL | Append-only event log + signals + predictions | `data/*.jsonl` |
| SQLite | Control-plane tasks + agent state | `services/control-plane/*.db` |
| JSON | Small registries (board, connectors, device topology) | `data/*.json` |
| BigQuery | Warehoused data lake | `tho-ai-agent.sapphire.*` |
| GCS | Raw NDJSON snapshots | `sapphire-data-lake/raw/<source>/YYYY-MM-DD/` |
| GCP Secret Manager | API tokens | pulled via `pull-gcp-secrets` task |

## 5. Control & Safety

- **Basic auth** gates the dashboard; `AUTH_PASSWORD` is mandatory (startup raises on empty).
- **Sensitivity classifier** blocks credentials/PnL/customer data from reaching Kimi Cloud.
- **Confirmation firewall** (`lib/core/confirmation_firewall.py`) requires explicit ack for destructive actions.
- **Runtime policy** (`data/agent_runtime_policy.json`) enumerates which agents may execute and which memberships the orchestrator honors.
- **Circuit breaker** halts trading on consecutive losses / latency spikes / drawdown thresholds.
- **Idempotency** (`execution_idempotency.py`) dedupes order submits by request ID.
- **Timing-safe auth** (`secrets.compare_digest`) in the dashboard login path.

## 6. Hardware / Network Topology

| Node | Addr | Role |
|------|------|------|
| Mac (commander) | 100.67.171.79 | inference-proxy, dashboard, control-plane, signal-logger, hermes, OpenBB, Redis, Ollama |
| Windows PC | 100.71.10.48 | RTX 5070 Ti (Ollama + 26 models), webhook :9090, telemetry-dashboard :3001 |
| Pi rari2 | 100.87.225.89 | ethernet, 3.8 GB RAM, online; signal-logger; Ollama pending install |
| Pi rari1 | 100.120.191.1 | offline (WiFi incompatible) |

Tailscale mesh connects everything. Cloudflare Tunnel exposes `webhook.sapphirealpha.xyz` → Windows :9090.

## 7. Where to start reading

1. **CLAUDE.md** — top-level project memory. Every future session reads this first.
2. **services/inference-proxy/app.py** — the best-documented large file; read if you need to understand the LLM routing.
3. **lib/core/src/sapphire_core/risk_kernel.py + circuit_breaker.py** — trading safety invariants.
4. **services/alpha/src/main.py** — trading engine orchestrator (150KB — use grep to navigate).
5. **plugins/claw-sapphire/plugin.json** — tool registry; every tool is one file under `tools/`.
6. **docs/routines-manifest.md** (if present in main repo, currently uncommitted) — schedule reference.

## 8. Out-of-scope references

The CLAUDE.md in this worktree intentionally documents only what is **committed** to branch `claude/nifty-curran-f07e26`. The main repo has additional uncommitted modules (`lib/chain/`, several `docs/*.md`) that will land in future PRs — they are not wired into the worktree's service graph yet.
