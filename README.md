# Sapphire OS

> Self-sovereign AI operations platform for quantitative trading, intelligence, and content.

![Tests](https://img.shields.io/badge/tests-1978%20passing-brightgreen)
![CI](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml/badge.svg?branch=main)
![Security](https://github.com/arigatoexpress/Sapphire/actions/workflows/security.yml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-proprietary-lightgrey)

Sapphire is a continuously-running operating system for capital allocation and research. It runs on a four-node on-prem cluster (Mac M4 Pro commander, RTX 5070 Ti Windows GPU, two Raspberry Pis), uses GCP only as a data lake, and is governed through a Telegram heartbeat. Every signal, inference call, publication, and trade is observable on the event bus, auditable in the dashboard, and (where applicable) anchored on-chain.

> `Net PnL = (edge × trades × capital efficiency) − (fees + slippage + infra + tail losses)`

---

## Architecture

```
  CONTROL PLANE
  -------------
  Telegram  -->  hermes gateway  -->  Inference Proxy :11435
  operator                            4-tier failover:
                                        T1 Windows GPU  (RTX 5070 Ti)
                                        T2 Pi rari1 / rari2
                                        T3 Mac Ollama (CPU)
                                        T4 Kimi Cloud (non-sensitive)

  TRADING PATH
  ------------
  TradingView --> webhook :9090 --> signal-logger :18081 --> Risk Kernel
  (Pine)         (Windows)          (Mac)                    circuit breaker
                                                             position sizing
                                                             confirmation firewall
                                                                  |
                                    +-----------------------------+--------------+
                                    v                             v              v
                             Paper portfolio             Robinhood Crypto   Robinhood
                             ($100K sim, ATR SL/TP)      (Ed25519 REST)     Chain
                                                                            (on-chain
                                                                             signals)

  EVENT BUS  (Redis primary, JSONL fallback at data/events/bus.jsonl)
  ---------
     ^ producers          v consumers
     |                    |
     |  Risk kernel       +--> Dashboard :8080  (31 pages, SSE)
     |  Chain intel       +--> Content engine   (weekly auto-publish)
     |  Threat intel      +--> Telegram alerts  (priority-tagged)
     |  Strategies        +--> Foundry sync ----> Palantir Foundry ontology
     |  Heartbeat              (15-min delta)    (PaperTrade, Signal,
     |                                            ChainMetric, ThreatAlert)
     +--- Security platform (deps, models, network, heartbeat, kill switches)

  SIDECARS
  --------
  Control Plane :8082  (projects, tasks, Kimi bridge)
  gcp_sync (hourly)    --> GCS data lake + BigQuery sapphire.*
```

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Passing unit + plugin tests | **1,978** (1,943 core + 35 plugin) |
| Dashboard pages | **31** |
| Quant strategies (`lib/analytics/strategies.py`) | **7** |
| Pine Script strategies | **5** |
| Plugin tool scripts | **32** (16 registered, 24 internal, 1 deprecated) |
| LaunchAgents (Mac) | **10** plists |
| Claude Code scheduled tasks | **21** |
| Smart contracts (`contracts/`) | **2** Solidity |
| Data providers wired | **13** |
| Inference tiers | **4** (GPU · Pi · Mac · Kimi Cloud) |
| Content publishers | **4** (Substack · X · LinkedIn · Typefully) |

---

## Trading System

### Seven Quant Strategies (`lib/analytics/strategies.py`)

| Strategy | Core idea |
|----------|-----------|
| `RegimeAwareRSI` | RSI reversion gated by GMM regime classification |
| `FundingRateContrarian` | Fades extreme perps funding skew (`lib/chain/` data) |
| `CorrelationBreakout` | Enters on cross-asset correlation breaks |
| `MultiTFMomentum` | Multi-timeframe momentum confirmation |
| `SapphireComposite` | Ensemble of the above, regime-weighted |
| `Strategy` (base) | Abstract runtime shared by all above |
| `StrategyParams` | Typed parameter registry |

### Rigor
- **CPCV** — combinatorial purged cross-validation (`lib/analytics/cpcv.py`)
- **Regime detection** — GMM over volatility + trend (`lib/analytics/regime.py`)
- **VPIN** — volume-synchronized probability of informed trading
- **Deflated Sharpe / Sortino / Calmar** — `risk_engine.py`, `deflated_sharpe.py`
- **Walk-forward backtests** — `backtest_engine.py`, artifacts under `data/backtests/`

### Pipeline
`TradingView Pine → Windows webhook :9090 → Mac signal-logger :18081 → Redis → risk kernel → paper + Robinhood execution`.
Paper portfolio: $100K notional, ATR-based SL/TP (1.67 : 1 R : R), 10% position sizing, runs alongside live.

### Prediction accuracy (24 scored predictions)
| Asset | Accuracy |
|-------|----------|
| BTC | **75%** |
| ETH | 62% |
| SOL | 38% |
| Overall | **58%** |

---

## Data Sources

| Provider | Module | Auth | Data |
|----------|--------|------|------|
| CoinMetrics | `lib/chain/coinmetrics.py` | API key | On-chain fundamentals |
| DeFiLlama | `lib/chain/sources.py` | none | TVL, protocol metrics |
| Hyperliquid | `lib/chain/sources.py` | none | L1 perps order book |
| CoinGecko | `lib/chain/sources.py` | none | Market caps, prices |
| CoinGlass | `lib/chain/providers/coinglass.py` | API key | Options, liquidations, OI |
| Dune Analytics | `lib/chain/providers/dune.py` | API key | Custom SQL queries |
| Whale Alert | `lib/chain/providers/whale_alert.py` | API key | Large transactions |
| Santiment | `lib/chain/providers/santiment.py` | API key | Social + on-chain |
| CoinAPI | `lib/chain/providers/coinapi.py` | API key | OHLCV + reference |
| BGGeometrics | `lib/chain/providers/bgeometrics.py` | API key | On-chain metrics |
| OpenBB | REST `:6900` | none | Equity + crypto OHLCV |
| Robinhood Crypto | `lib/portfolio/robinhood.py` | **Ed25519 keypair** | Portfolio, holdings, orders |
| FRED | REST | API key | Macro indicators |
| CISA / NVD | REST | none | Vulnerability intel |

---

## Security Platform

A full second-class-citizen security stack — not an afterthought.

| Module | Role |
|--------|------|
| `lib/security/dependency_scanner.py` | CVE lookup via OSV.dev, outdated-package detection, **CycloneDX 1.5 SBOM** emission |
| `lib/security/model_monitor.py` | SHA-256 verification of Ollama model blobs against manifest digests; Jinja2 template backdoor detection |
| `lib/security/network_mapper.py` | Tailscale topology enumeration, port probes, trust-zone classification, attack-surface scoring |
| `lib/core/heartbeat.py` | 60 s per-component state machine (HEALTHY → DEGRADED → FAILED → RECOVERING) with Telegram escalation + self-heal |
| `lib/core/security_monitor.py` | Runtime anomaly detection, event-bus publish on suspicious activity |
| `lib/core/security_kill_switch.py` | Per-service kill switch, fails-closed at policy violation |
| `lib/core/kill_switch.py` | Global trading kill switch (circuit breaker) |
| `lib/core/confirmation_firewall.py` | Two-phase-commit gate on any action that mutates capital or external state |
| `lib/core/decision_engine.py` | Ranks + explains every autonomous decision before it executes |
| `plugins/claw-sapphire/lib/sensitivity_classifier.py` | Regex block on PII/secrets before egress to Kimi Cloud |
| `services/security_pipeline/` | Scheduled full-system scan, ships findings to SOC page |

Perimeter: **Tailscale mesh-only**. No open ingress ports. Secrets live in **GCP Secret Manager** or `~/.sapphire/secrets.env` (mode 0600, never in plists).

See [`docs/opus-audit-2026-04-17.md`](docs/opus-audit-2026-04-17.md) for the hardening audit and [`docs/nist-alignment.md`](docs/nist-alignment.md) for the NIST CSF control map.

---

## Content Engine

`lib/content/` — a 14-module research-to-publish pipeline with an institutional-grade quality gate.

| Stage | Module |
|-------|--------|
| Signal collection | `data_collector.py` (event-bus aggregation) |
| Thesis generation | `thesis_engine.py` |
| Draft rendering | `draft_generator.py`, `report_generator.py` |
| Visualization | `visualizations.py` |
| Quality gate | `quality.py` — seven-check institutional rubric |
| Performance policy | `performance_policy.py` — blocks accuracy boasts before sample size supports them |
| QA pipeline | `qa_pipeline.py` |
| Formatting | `formatters.py` — platform-specific rendering |
| Approval | `approval.py` — Telegram-based human sign-off |
| Publishing | `publisher.py`, `auto_publish.py` + publishers: `substack`, `x`, `linkedin`, `typefully` |
| Scheduling | `scheduler.py` — Mon weekly brief · Wed AI intel · Fri security digest · daily market pulse |
| Outreach | `outreach.py` — lead engine integration |

Runs weekly via `com.sapphire.content-engine` LaunchAgent. CLI: `python3 -m lib.content generate` / `publish`.

**Quality rubric (`quality.py`):** evidence density, evidence coverage, citation quality, unsupported-conclusion detection, argument coherence, originality, small-sample performance-claim block.

---

## Integrations

### Robinhood Crypto API — live portfolio
`lib/portfolio/robinhood.py`. Ed25519-signed REST requests against `trading.robinhood.com`. Reads accounts, holdings, best bid/ask, and order history; reconstructs weighted-average cost basis from filled orders. Credentials in `~/.config/sapphire-secrets/`.

### Robinhood Chain (Arbitrum Orbit, chain ID 46630) — on-chain signal anchoring
`lib/chain/robinhood_chain.py` + `contracts/`:
- **`SapphireSignalVerifier.sol`** — on-chain signal registry: `publishSignal(strategyId, symbol, direction, confidence, proofHash)`, with operator-controlled verification.
- **`SapphirePaymentGate.sol`** — micropayment gate for paid inference / data calls.

Deployment script: `scripts/deploy_robinhood_chain.py`. Deployed addresses in `data/chain/deployments.json`. Dashboard page: `/robinhood_chain`.

### Palantir Foundry
`lib/foundry/` + `services/foundry_sync/`:
- `client.py` — SDK wrapper, bearer-token + OAuth client-credentials auth.
- `ingestion.py` — transforms local JSONL/data → Foundry ontology objects.
- `readiness.py` — repo-grounded readiness audit.
- `sync.py` — 15-min delta-aware scheduled sync, Telegram alerts on drift.

Ontology objects: `PaperTrade`, `Signal`, `ChainMetric`, `ThreatAlert`, plus scheduled syncs for strategy performance + regime snapshots. Schema: [`docs/foundry-ontology-schema.md`](docs/foundry-ontology-schema.md). Strategy: [`docs/foundry-strategy-2026-04-19.md`](docs/foundry-strategy-2026-04-19.md).

### TradingView CDP
Chrome DevTools Protocol-driven TradingView Desktop. `tv` CLI (`tv status`, `tv quote`, `tv pine compile`, `tv stream all`). Setup: [`docs/tradingview-cdp-setup.md`](docs/tradingview-cdp-setup.md).

### GCP BigQuery + GCS
`services/pipeline/gcp_sync.py`. Hourly watermarked sync of event bus → `sapphire-data-lake/raw/<source>/YYYY-MM-DD/` + `tho-ai-agent.sapphire.{signals,predictions,market_regime,threats,…}`. Schema doc: [`docs/gcp-data-engineering.md`](docs/gcp-data-engineering.md).

### Other satellite integrations
x402 (Coinbase HTTP 402 micropayments), Hermes Agent (NousResearch, Telegram), Kimi Cloud fallback, Claw Code Rust runtime (plugin host).

---

## Dashboard (31 pages)

`services/dashboard/` — Flask + SSE, basic-auth protected, 10 s cached fetchers.

| Category | Pages |
|----------|-------|
| **Command** | overview · command_deck · control · system · settings · platform |
| **Trading** | signals · predictions · portfolio · performance · sapphire_book · risk |
| **Intelligence** | intel · intelligence · chain · cascade · factors · agents |
| **Content & ops** | content · organization · activity · logs |
| **Security** | soc · security · health · infrastructure · production_readiness |
| **Architecture** | architecture · analytics |
| **Integrations** | robinhood_chain · admin_domains |

SSE event stream at `/api/events/stream`. Performance endpoints wired to real trade data: `/api/strategy-performance`, `/api/performance-timeseries`, `/api/backtest-results`, `/api/forecast`.

---

## Tool Architecture

`plugins/claw-sapphire/` — claw-code plugin host.

```
tools/
├── <name>.py              registered (8, agent-facing; in plugin.json)
├── internal/<name>.py     internal   (24, invoked by scheduled tasks / hermes / services)
└── _deprecated/<name>.py  deprecated (1, in sunset window)
```

**Registered (agent-facing, 15 tools + 1 namespace):** `dispatch`, `verify`, `budget`, `state`, `status`, `notify`, `health_check`, `market`, `predict_kronos`, `threat_intel`, `lumo_research`, `starred_repos`, `macro_data`, `lead_engine`, `trading_brain`.

**Agent manifest** (`infra/agent-manifest.yaml`) — the lean 5-tool subset the LLM actually sees: `sapphire_market`, `sapphire_dispatch`, `sapphire_notify`, `sapphire_verify`, `sapphire_state`.

**Registry invariants (CI-enforced by `scripts/validate_tool_registry.py`):**
1. Every `.py` under `tools/` is in the registry (`infra/tool-registry.yaml`).
2. Every registered tool file exists and parses.
3. Every deprecated entry has a `warnings.warn(..., DeprecationWarning)` shim.
4. `agent-manifest.yaml` is a strict subset of registered + `agent_facing: true`.

**Shared libraries (10):** `technical_analysis`, `nemotron`, `quant_analysis`, `router`, `runtime_policy`, `token_governor`, `sensitivity_classifier`, `market_data`, `nvidia_agents`, `budget`.

---

## Smart Contracts

`contracts/` — deployed to Robinhood Chain testnet (Arbitrum Orbit, chain ID 46630).

| Contract | Purpose |
|----------|---------|
| `SapphireSignalVerifier.sol` | On-chain trading signal registry with operator-controlled verification and ZK-proof hash field for future verifiable computation |
| `SapphirePaymentGate.sol` | Micropayment gate for paid inference / data endpoints |

Deployment: `scripts/deploy_robinhood_chain.py`. Foundry config: `foundry.toml`. Addresses tracked in `data/chain/deployments.json`.

---

## Hardware Topology

| Node | Role | Specs |
|------|------|-------|
| Mac M4 Pro (`100.67.171.79`) | Commander — all LaunchAgents, dashboard, signal logger, inference proxy, hermes gateway, OpenBB, Redis | M4 Pro, 48 GB unified RAM |
| Windows GPU (`100.71.10.48`) | T1 inference + TradingView webhook + telemetry | RTX 5070 Ti 16 GB, Ollama with 28 models |
| Pi `rari1` (`100.120.191.1`) | T2 inference | nemotron-mini, qwen2.5:0.5b, gemma2:2b, smollm2:1.7b |
| Pi `rari2` (`100.87.225.89`) | T2 inference | Same roster as rari1 |

**Mesh:** Tailscale — all inter-node traffic; ACL at `infra/tailscale-acl.json`. **SSH:** `ssh aribs@100.71.10.48` (Windows), direct access to Pis for ops.

### Inference Proxy (`services/inference-proxy/`)

| Tier | Host | Latency | Notes |
|------|------|---------|-------|
| T1 Windows GPU | `100.71.10.48:11434` | ~0.4 s | Native `/api/chat` (Windows Ollama `/v1/` returns empty) |
| T2 Pi cluster | rari1 + rari2:`11434` | ~2–5 s | Lightweight models only; sensitivity-safe |
| T3 Mac Ollama | `127.0.0.1:11434` | ~90 s | CPU inference fallback |
| T4 Kimi Cloud | `api.moonshot.cn` | varies | Non-sensitive only — sensitivity classifier gates |

**Model aliases:** `fast`/`quick` → nemotron-mini · `auto`/`balanced` → hermes3:8b · `deep` → qwen3:14b · `code` → gemma4 · `reason` → deepseek-r1:14b · `qwen-reason` → qwen3.5:9b · `qwen3.6` → qwen3.6:27b (Mac exact fallback until Windows install) · `cascade`/`moe` → nemotron-cascade-2 · `large` → qwen2.5:32b · `kimi` → kimi-cloud.

**Endpoints:** `/v1/chat/completions` · `/v1/models` · `/health` · `/metrics` · x402-gated (optional).

---

## Quick Start

```bash
# Requirements: Python 3.11+, Redis, Ollama, ruff

# 1. Install
pip install -r services/alpha/requirements.txt
pip install -r services/dashboard/requirements.txt

# 2. Secrets
cp env.example .env
cp .env.integrations.example .env.integrations
export AUTH_PASSWORD=sapphire
export TELEGRAM_BOT_TOKEN=<@BotFather>
export SAPPHIRE_CONTROL_API_TOKEN=<random-hex>

# 3. Core services (or let the LaunchAgents in infra/launchagents/ run them)
python3 services/inference-proxy/app.py &                          # :11435
(cd services/alpha && python3 -m uvicorn src.signal_logger:app --port 18081) &
(cd services/dashboard && python3 app.py) &                        # :8080
(cd services/control-plane && uvicorn app.main:app --port 8082) &

# 4. Health
curl -s http://127.0.0.1:11435/health | python3 -m json.tool
curl -s http://127.0.0.1:18081/health

# 5. Plugin tools (all read stdin JSON)
echo '{"action":"quote","symbol":"BTC/USDT"}' | python3 plugins/claw-sapphire/tools/market.py
echo '{"action":"predict"}'                    | python3 plugins/claw-sapphire/tools/internal/predict.py

# 6. Content
python3 -m lib.content generate
python3 -m lib.content publish
```

---

## Testing

```bash
# Unit tests — 1,943 passing
/usr/local/bin/python3 -m pytest tests/unit/ --tb=short -q

# Plugin tests — 35 passing
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q

# Lint
ruff check .
ruff check --fix .

# Tool registry invariant
python3 scripts/validate_tool_registry.py
```

> **Mac gotcha:** `python3` may resolve to Homebrew 3.14 (no pytest). Use `/usr/local/bin/python3`.

---

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Target chat/channel ID |
| `AUTH_PASSWORD` | Yes | Dashboard basic-auth password |
| `SAPPHIRE_CONTROL_API_TOKEN` | Yes | Control-plane token (fails-closed 503 if unset) |
| `MOONSHOT_API_KEY` | No | Kimi Cloud fallback (in `~/.sapphire/secrets.env`) |
| `ANTHROPIC_API_KEY` | No | Claude API access |
| `GEMINI_API_KEY` | No | Gemini integration |
| `VIRUSTOTAL_API_KEY` | No | Threat analysis |
| `GOOGLE_APPLICATION_CREDENTIALS` | No | GCP sync ADC JSON |
| `GOOGLE_CLOUD_PROJECT` | No | GCP project (default `tho-ai-agent`) |
| `PALANTIR_FOUNDRY_URL` | No | Foundry stack URL |
| `PALANTIR_FOUNDRY_TOKEN` | No | Foundry bearer token |
| `X402_ENABLED` | No | Enable x402 paywall on inference proxy |
| `PI_RARI1_ENABLED` / `PI_RARI2_ENABLED` | No | Route inference to Pi nodes |
| `ROBINHOOD_CHAIN_RPC` | No | Robinhood Chain RPC endpoint |

Content + chain provider keys live in `.env.integrations`. Production secrets in GCP Secret Manager. **Never commit real values.**

---

## Revenue Pipelines

| Pipeline | Status | Description |
|----------|--------|-------------|
| Trading — paper | Active | Autonomous signal generation with full risk stack |
| Trading — Robinhood Crypto | Wired | Live account read; execution behind confirmation firewall |
| THO client delivery | Active | PM deliverables via control-plane → Cloud Run |
| Elite Net outreach | Active | Lead engine, enrichment, autonomous daily outreach |
| x402 inference | Implemented | HTTP 402 micropayment gate on inference proxy |
| Content | Active | Weekly automated report → Substack + X + LinkedIn + Typefully |
| Buildathon (London) | Pitch-ready | Foundry ontology + Robinhood Chain showcase |

---

## Research

The `docs/` directory is 400K+ words of cross-validated architecture, audit, and planning work.

| Document | Purpose |
|----------|---------|
| [`docs/architecture-overview.md`](docs/architecture-overview.md) | Full module wiring, request lifecycles, data flows |
| [`docs/opus-audit-2026-04-17.md`](docs/opus-audit-2026-04-17.md) | Security audit — source of current hardening |
| [`docs/nist-alignment.md`](docs/nist-alignment.md) | NIST CSF control map |
| [`docs/crypto-integrations-plan.md`](docs/crypto-integrations-plan.md) | x402, Zama FHE, Ika MPC, Aztec Noir, Robinhood Chain |
| [`docs/foundry-strategy-2026-04-19.md`](docs/foundry-strategy-2026-04-19.md) | Palantir Foundry value thesis + integration plan |
| [`docs/foundry-ontology-schema.md`](docs/foundry-ontology-schema.md) | Foundry object-type schema (PaperTrade, Signal, ChainMetric, ThreatAlert) |
| [`docs/palantir-foundry-strategy-2026-04-19.md`](docs/palantir-foundry-strategy-2026-04-19.md) | Partnership-facing Foundry strategy |
| [`docs/gcp-data-engineering.md`](docs/gcp-data-engineering.md) | Data lake design, BigQuery schema |
| [`docs/kronos-integration-plan.md`](docs/kronos-integration-plan.md) | Kronos ML forecasting architecture |
| [`docs/tradingview-cdp-setup.md`](docs/tradingview-cdp-setup.md) | TradingView CDP setup |
| [`docs/QUICK_START_GUIDE.md`](docs/QUICK_START_GUIDE.md) | First-run setup |
| [`docs/LOGGING.md`](docs/LOGGING.md) | Event + audit log schema |
| [`docs/setup/`](docs/setup/) | Windows bringup, Pi Ethernet bridge, Cloudflare DNS |

---

## Satellite Repositories

| Repo | Role |
|------|------|
| `instructkr/claw-code` | Rust agent runtime (plugin host) |
| `arigatoexpress/Project-Go-Forward` | THO client PM |
| `arigatoexpress/regional-intel-workbench` | Regional intelligence platform |
| `arigatoexpress/tradingview-mcp` | TradingView MCP server |
| `arigatoexpress/crypto-tax-tracker` | Crypto tax engine |
| `arigatoexpress/cyber-threat-bot` | Threat intel feeds |
| `NousResearch/hermes-agent` | Telegram conversational gateway |

---

## License

Proprietary — see [`LICENSE`](LICENSE). All research, strategies, and implementations are private. Do not distribute.
