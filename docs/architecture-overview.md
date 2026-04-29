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

### Services (19)

| Service | Runtime | Port | Purpose |
|---------|---------|------|---------|
| alpha | uvloop | 18081 | Trading engine: signals, risk kernel, execution, self-improvement. `src/main.py` orchestrates; `src/signal_logger.py` exposes :18081. |
| analytics_dashboard | Flask | — | Analytics-focused dashboard variant. |
| aster | async Python | — | Aster DEX (Solana) perpetuals bot. Shield HFT strategy. (Paused.) |
| control-plane | FastAPI | 8082 | PM hub. Projects, tasks, JSONL event stream, Kimi dispatch bridge, runtime policy. |
| dashboard | Flask | 8080 | Ops surface. 43 pages incl. `/showcase`, `/threat-intel`, `/customer-dossier`, `/sovereign-thesis`, and `/inference-telemetry`. Basic-auth. |
| foundry_sync | Python | — | Scheduled Palantir Foundry sync daemon (15-min delta-aware + Telegram alerts). |
| heartbeat | Python | — | 60s state-machine heartbeat daemon wrapper. |
| hyperliquid | async Python | — | Hyperliquid L1 perps. (Stub at this writing — see `feat/hyperliquid-signal-subscription`.) |
| inference-proxy | stdlib http.server | 11435 | 4-tier LLM failover, OpenAI-compatible. |
| intelligence | Python | — | Daily brief generator + chain refresh. |
| morning_digest | Python | — | Scheduled morning operational digest (consumes `dev_pulse`). |
| openbb_api | Uvicorn | 6900 | OpenBB Platform REST surface (32 financial-data providers). |
| pipeline | CLI | — | GCP data-lake sync (BigQuery + GCS). |
| pm_bot | Python | — | Telegram-first PM bot daemon (wraps the `sapphire_pm_bot` plugin tool). |
| scout-sandbox | Python | — | GTM outbound + web-intel broker. Env-guarded. |
| security_pipeline | Python | — | Scheduled full-system security scan → SOC page. |
| service_supervisor | Python | — | Self-healing LaunchAgent supervisor (per-label cooldowns, restart cap, sparse Telegram escalation). |
| telegram-bot | FastAPI | 8088 | Thin claw-code webhook (legacy; replaced by hermes-agent for live ops). |
| webhook (Windows) | — | 9090 | TradingView → HMAC-verified → signal_logger. |

### Libraries

- **lib/core/src/sapphire_core/** — risk kernel, circuit breaker, position sizing, models, pub/sub clients, logging, health, cognitive mesh, episodic memory, error classifier, confirmation firewall, execution idempotency, symbol resolver, neural cache, smart notifications.
- **lib/agents/src/sapphire_agents/** — orchestrator (master), OpenClaw/NemoClaw dispatch, runtime policy whitelist, token governor.
- **lib/analytics/** — correlation matrix, risk engine.
- **lib/telegram/src/sapphire_telegram/** — bot + command handlers.

### Plugin (`plugins/claw-sapphire/`)

40 tool entries in the registry (7 registered / 32 internal / 1 deprecated) — source of truth is `infra/tool-registry.yaml`. 10 shared libraries under `plugins/claw-sapphire/lib/`. The agent-facing manifest stays lean (5 tools) — research shows tool-selection accuracy drops from 74% → 49% as manifest grows.

### Scheduled routines (23)

Run when Claude Code is open; all under `~/.claude/scheduled-tasks/<name>/SKILL.md`. Morning briefing (8 AM) and evening digest (6 PM) bookend the day. Trading loop: trading-research (5:42) → market-pulse (every 4h) → self-improvement (8:53 PM). Routines are pausable via the Telegram operator console (`/routines pause <name>` drops `~/.sapphire/routine_pause/<name>`).

### Acquisition surfaces (Wave 4)

Buyer-readable product surfaces shipped 2026-04-28:

- `docs/products/risk-kernel-0.1.0.md` — public risk-kernel surface (PR #331).
- `docs/products/provenance-envelopes-0.1.0.md` — `{generator, model, prompt_hash, source_hashes, ttl, version}` stamps on every generated artifact (PR #334).
- `docs/products/threat-intel-product-0.1.0.md` + `/threat-intel` route — paste-safe threat-intel summary (PR #374).
- `docs/products/customer-dossier-product-0.1.0.md` + `/customer-dossier` route — PII-redacted dossier surface (PR #374).
- Vertex eval harness — bounded Gemini OODA scoring for the Vertex spend (PR #372).
- BigQuery vector retrieval — mock-default semantic search over the intel corpus (PR #376; live BQ + real Vertex embedder are tranche-2 follow-ups).
- Telegram operator console — `/health`, `/services`, `/routines pause|resume`, `/digest`, secret-denylist regex, fail-closed allowlist (PR #373).
- `docs/diligence/00`–`09` — acquisition packet (PR #341).

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
| Pi rari2 | 100.87.225.89 | ethernet, 3.8 GB RAM, online; Ollama 4 models (`PI_RARI2_ENABLED=0` post-2026-04-28 plist drift fix). |
| Pi rari1 | 100.120.191.1 | online via Tailscale; Ollama 4 models; SSH refused (needs physical access to start sshd). |

Tailscale mesh connects everything. Cloudflare Tunnel exposes `webhook.sapphirealpha.xyz` → Windows :9090.

## 7. Where to start reading

1. **CLAUDE.md** — top-level project memory. Every future session reads this first.
2. **services/inference-proxy/app.py** — the best-documented large file; read if you need to understand the LLM routing.
3. **lib/core/src/sapphire_core/risk_kernel.py + circuit_breaker.py** — trading safety invariants.
4. **services/alpha/src/main.py** — trading engine orchestrator (150KB — use grep to navigate).
5. **plugins/claw-sapphire/plugin.json** — registry for the 12 Claude Code tools; companion stdin-JSON scripts also live under `plugins/claw-sapphire/tools/`.
6. **docs/routines-manifest.md** (if present in main repo, currently uncommitted) — schedule reference.

## 8. Out-of-scope references

The CLAUDE.md in this worktree intentionally documents only what is **committed** to branch `claude/nifty-curran-f07e26`. The main repo has additional uncommitted modules (`lib/chain/`, several `docs/*.md`) that will land in future PRs — they are not wired into the worktree's service graph yet.
