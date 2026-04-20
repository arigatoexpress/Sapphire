# Sapphire OS — Collaborator / Developer Pack

*Verified 2026-04-19. See [README.md](README.md) for how to report drift.*

---

## 1. What Sapphire is, in one paragraph

Sapphire is a **self-sovereign, Telegram-operated, event-bus-mediated AI
operations platform** running quantitative crypto trading, market/threat
intelligence, and an institutional-quality content engine off a **4-node
on-prem mesh** (Mac commander, Windows GPU, two Raspberry Pis). GCP is used
only as a downstream data lake. The critical path — LLM inference, trade
execution, signal routing, secret storage — stays local. Nothing in the hot
path depends on a SaaS that could rug-pull.

**Tagline:** `Net PnL = (edge × trades × capital efficiency) − (fees + slippage + infra + tail losses)`.

## 2. Topology

```
                                Cloudflare Tunnel (external access)
                                           │
                                           ▼
┌───────────────────────────── Tailscale mesh (6 ACL trust zones) ────────────────────────────────┐
│                                                                                                  │
│   Mac M4 Pro 24GB (100.67.171.79) — commander                                                   │
│   ├── control-plane  :8082       ├── dashboard :8080      ├── signal-logger :18081              │
│   ├── inference-proxy :11435     ├── content-engine       ├── hermes-agent gateway (Telegram)   │
│   ├── Redis :6379                ├── Ollama :11434        └── OpenBB :6900                      │
│                                                                                                  │
│   Windows RTX 5070 Ti 16GB (100.71.10.48) — GPU + webhook                                       │
│   ├── Ollama :11434 (28 models, OLLAMA_HOST=0.0.0.0)   └── TradingView webhook :9090            │
│                                                                                                  │
│   Pi rari1 (100.120.191.1) — small-model research       Pi rari2 (100.87.225.89) — backup      │
│   └── Ollama :11434 (4 tiny models)                     └── Ollama :11434 (5 models)            │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Event fabric:** Redis Streams primary, JSONL file fallback at
`data/events/bus.jsonl` (degrades gracefully). Every signal, LLM call,
publication, and trade emits an event → dashboard SSE stream, content engine,
Telegram alerts, and Palantir Foundry ontology sync consume from the same bus.

**LLM inference routing** — a 4-tier failover proxy at `:11435`:
- **T1** Windows GPU — fast local (native `/api/chat`)
- **T2** Pi cluster — tiny models (`nemotron-mini`, `gemma2:2b`, `qwen2.5:0.5b`)
- **T3** Mac Ollama — CPU fallback (`/v1/chat/completions` passthrough)
- **T4** Kimi Cloud / Moonshot — **only for non-sensitive content**, gated by a
  regex sensitivity classifier. Health-probed every 30s with 60s cooldown.

## 3. The four pillars

### 3.1 Quant trading
Seven strategies (`lib/analytics/strategies.py`): `RegimeAwareRSI`,
`FundingRateContrarian`, `CorrelationBreakout`, `MultiTFMomentum`,
`SapphireComposite`, `CVDOrderFlow`, `VolatilityBreakout`. Stats rigor: GMM
3-state regime detection, VPIN flow toxicity filter, CPCV with 15 purged
splits, deflated Sharpe, liquidation cascade detector, quarter-Kelly with vol
ceiling. Pipeline:

```
TradingView Pine  →  Windows webhook :9090  →  Mac signal-logger :18081
                 →  Redis  →  risk kernel  →  paper + Robinhood Crypto execution
```

Paper portfolio runs alongside live at $100K notional, ATR-based SL/TP
(1.67 : 1 R : R), 10 % position sizing. Current scored accuracy: **58 %
overall, BTC 75 %** over 24 predictions.

### 3.2 Market + threat intelligence
Live connectors: CoinMetrics, DeFiLlama, Hyperliquid, CoinGecko, CoinGlass,
Dune, Whale Alert, Santiment, BGGeometrics. Threat intel: CISA / NVD / OSV.dev
pulled by scheduled tasks. All tagged and event-bussed.

### 3.3 Content engine
14-module research-to-publish pipeline (`lib/content/`):
`data_collector → thesis_engine → draft_generator → report_generator →
visualizations → quality (7-check rubric) → performance_policy (blocks
premature accuracy claims) → qa_pipeline → formatters → approval (Telegram
sign-off) → publisher`. Four publishers (Substack, X, LinkedIn, Typefully).
Bilingual EN/ES (130-term glossary). SEC disclaimers auto-appended. **Nothing
ships without explicit Telegram approval.**

### 3.4 Ops / infra
- `lib/core/heartbeat.py` — 60 s sweep, `HEALTHY → DEGRADED → FAILED →
  RECOVERING` state machine, self-heal via `launchctl kickstart`.
- Daily 3 AM security pipeline: dep CVE, model integrity, network mapper, PII
  scanner, kill-switch test, SBOM generation.
- 21 Claude Code scheduled tasks, 10 macOS LaunchAgents.
- Palantir Foundry sync every 15 min (ontology objects: `PaperTrade`, `Signal`,
  `ChainMetric`, `ThreatAlert`).
- Two Solidity contracts on Robinhood Chain (Arbitrum Orbit testnet, chain
  ID 46630): `SapphireSignalVerifier`, `SapphirePaymentGate`.

## 4. Scale (verified 2026-04-19)

| | |
|---|---|
| Python tests passing | **1,967** (1,932 core + 35 plugin) |
| Dashboard pages | 31 |
| Plugin tools | 32 (8 agent-facing, 24 internal, 1 deprecated) |
| Quant strategies | 7 |
| Scheduled tasks | 21 |
| LaunchAgents (on disk, enabled) | 10 |
| Inference tiers / models (GPU) | 4 / 28 |
| Data providers | 13 |
| Content publishers | 4 |
| Smart contracts | 2 Solidity |
| Tailscale ACL trust zones | 6 |

## 5. Security posture (the part to audit)

- **Secrets at rest:** SOPS + age encryption; `~/.config/sapphire-secrets/`
  with mode `700`; one file per credential. See `infra/setup-sops.sh`.
- **Network:** Tailscale-only plane, six ACL trust zones, Cloudflare Tunnel
  for externals, zero public SSH.
- **Supply chain:** CycloneDX 1.6 SBOM daily, OSV.dev CVE lookup, `gitleaks`
  at pre-commit **and** in CI, `.git-secrets-patterns` regex, sigstore
  artifact signing.
- **Model integrity:** Ollama blobs fingerprinted with SHA-256; Jinja2
  template scanner checks for 7 known backdoor patterns (see
  `lib/security/model_monitor.py`). Local models for anything sensitive; cloud
  tier is regex-gated by the sensitivity classifier in
  `plugins/claw-sapphire/lib/sensitivity_classifier.py`.
- **Runtime guardrails:** portfolio kill switch + emergency kill switch
  (global), confirmation firewall (2-phase commit) before irreversible
  actions, decision engine with explainable autonomous ranking, position
  sizing returns 0 on unknown `execution_stage` (fail-safe default).
- **Observability:** every action is an event; `data/system_events.jsonl` is
  tamper-evident append-only. Daily security scan posts grade to the SOC page.
  Last grade: **C (70 / 100)**, 283 deps tracked, 0 secret leaks.
- **Agent harness:** `.claude/settings.json` `PreToolUse` hook **blocks
  Edit / Write** to `*secrets*`, `*.env`, PII files, trading signals,
  `keys.txt`, `sapphire-secrets` *before* the tool call executes (exit 2 with
  reason string to the agent).

## 6. Repo layout (what to know)

```
Sapphire/
├── lib/                       # pure libraries (no sys-level I/O)
│   ├── analytics/             # 26 modules — strategies, regime, VPIN, backtest, risk_engine
│   ├── chain/                 # on-chain intelligence + Robinhood Chain web3 client
│   ├── content/               # 14-module research-to-publish pipeline
│   ├── core/                  # risk kernel, event_bus, heartbeat, kill_switch, firewall
│   ├── foundry/               # Palantir Foundry SDK (bearer + OAuth)
│   ├── portfolio/             # Robinhood Crypto Ed25519 client
│   ├── security/              # dep scanner + SBOM, model monitor, network mapper
│   ├── intel/                 # market intelligence + lead enricher
│   ├── payments/              # x402 micropayment middleware
│   ├── agents/                # OpenClaw / NemoClaw dispatch + runtime policy
│   ├── telegram/              # Telegram helpers (kimi_relay, login widget HMAC)
│   └── trading/               # Solana wallet
├── services/                  # services — never import from other services, only from lib/
│   ├── alpha/                 # trading engine + signal logger
│   ├── control-plane/         # :8082 PM hub
│   ├── dashboard/             # :8080 Flask dashboard (31 pages, SSE)
│   ├── inference-proxy/       # :11435 4-tier LLM router + x402 gate
│   ├── heartbeat/             # heartbeat daemon wrapper
│   ├── foundry_sync/          # scheduled Foundry sync
│   ├── security_pipeline/     # scheduled full-system scan
│   ├── intelligence/          # daily brief generator
│   ├── pipeline/              # GCP sync — events → GCS + BigQuery
│   └── webhook/               # TradingView webhook (Windows :9090)
├── plugins/claw-sapphire/     # 32 tools (8 top-level, 24 internal, 1 deprecated), 35 tests
├── contracts/                 # SapphireSignalVerifier.sol, SapphirePaymentGate.sol
├── pine/                      # 5 TradingView strategies
├── infra/                     # launchagents/, agent-manifest.yaml, tool-registry.yaml,
│                              # tailscale-acl.json, setup-sops.sh
├── skills/                    # agent-executable capabilities
├── tests/unit/                # 1,932 passing
├── scripts/ops/               # doctor.sh, ci_focused_gate.sh, backup_secrets.sh, ...
├── .github/workflows/         # ci.yml, security.yml
├── .pre-commit-config.yaml    # ruff + gitleaks + bandit + stdlib hooks
├── Makefile                   # `make help`
├── pyproject.toml             # single source of truth for ruff + pytest + bandit config
└── CLAUDE.md                  # project map for agents and humans
```

**Rule:** services never import from other services. Cross-service reuse goes
through `lib/`. Every module has a `SKILL.md` — read it before working on
that module.

## 7. Getting a dev environment running

### 7.1 Prerequisites
- **Python 3.11** — on Mac, use `/usr/local/bin/python3` (brew 3.14 often
  lacks pytest). Linux: standard `python3.11`.
- **Node 18+** — only if you're touching `services/dashboard/` frontend.
- **Ollama** — open-source, https://ollama.com. Pull at minimum
  `nemotron-mini` and `hermes3:8b` to exercise the inference proxy.
- **Redis** — `brew install redis && brew services start redis`, or optional
  (system will fall back to JSONL).
- **gh CLI** — `brew install gh`, `gh auth login`.
- **Tailscale** — **only if you need to reach the mesh.** For model red-team
  work, you don't. You can reproduce the whole inference stack locally.

### 7.2 One-shot setup

```bash
git clone https://github.com/arigatoexpress/Sapphire.git
cd Sapphire
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
make install-hooks        # pre-commit + commit-msg
make doctor               # environment sanity check — read the output
```

`make doctor` reports PASS / WARN / FAIL across toolchain, config files,
lint posture, secret-file hygiene, local service reachability, LaunchAgent
state, and git stale-branch detection. A clean first-time run on a laptop
without Tailscale looks like **~20 PASS, 2–4 WARN (no secrets dir, no
services running), 0 FAIL**.

### 7.3 Running tests

```bash
make test          # 1,932 core unit tests (~65 s)
make test-plugin   # 35 plugin tests (<1 s)
make test-all      # both
```

First run will be slower while pip caches resolve. If any test fails on a
clean checkout, it's a real regression — file an issue.

### 7.4 Running services locally

```bash
make dashboard        # :8080, needs AUTH_PASSWORD env (default "sapphire")
make control-plane    # :8082, needs CONTROL_PLANE_TOKEN (fails closed 503)
make signal-logger    # :18081
make inference-proxy  # :11435 with x402 gate enabled
```

### 7.5 Mirror CI locally before pushing

```bash
make ci               # ruff check + core tests + plugin tests + registry validation
```

This matches exactly what `.github/workflows/ci.yml` runs. If `make ci`
passes, GitHub CI will pass (modulo secrets-scan, which is GitHub-only).

## 8. Git + CI flow

1. **Branch:** `git checkout -b <your-handle>/<short-slug>`. Long-lived
   branches are fine; merge forward from `main` regularly.
2. **Commit:** small, atomic commits. Pre-commit runs ruff + gitleaks + bandit
   — **don't bypass it with `--no-verify`.** If a hook fails, fix the root
   cause.
3. **PR:** the template at `.github/pull_request_template.md` is mandatory.
   Fill out the "Risk touch points" checklist honestly — it's the signal
   reviewers need.
4. **CI:** `.github/workflows/ci.yml` runs five jobs on every PR (lint, core
   tests, plugin tests, tool registry, gitleaks). All must pass before merge.
5. **Review:** `.github/CODEOWNERS` gates security-sensitive, trading-critical,
   and infra paths — those PRs require Ari's explicit review. Non-gated paths
   can be merged after one +1.
6. **Merge:** squash-merge is preferred; keep the PR title useful as a commit
   title. Force-pushes to `main` are disabled.

## 9. Where to find answers

- **Commands:** `make help` or `CLAUDE.md` § Commands.
- **Architecture:** `docs/architecture-overview.md` (16 KB, module wiring).
- **Security:** `docs/nist-alignment.md` (NIST CSF controls),
  `docs/opus-audit-2026-04-17.md` (hardening source).
- **Foundry:** `docs/foundry-strategy-2026-04-19.md`,
  `docs/foundry-ontology-schema.md`.
- **First-run setup:** `docs/QUICK_START_GUIDE.md`.
- **Logging schema:** `docs/LOGGING.md`.

If an answer isn't in the repo, ask on Telegram — Ari's the single operator
and picks up fast. Don't DM with secrets; use the secure channel instead
(Signal, or ask Ari for preferred disclosure contact).

## 10. Access you'll probably want

| Resource | Who grants | Needed for |
|---|---|---|
| GitHub collaborator on `arigatoexpress/Sapphire` | Ari | pushing branches, reviewing PRs |
| Tailscale mesh invite | Ari | reaching the live dashboard / services at runtime |
| Telegram bot readonly access | Ari | observing events / approvals |
| Palantir Foundry workspace | Ari | only if working on ontology / Workshop |

For the AI model red-team scope specifically, **you don't need any of these
at first.** You can reproduce the entire inference tier locally with Ollama
and replay the sensitivity classifier and Jinja2 scanner on a laptop. See
[ai-redteam-scope.md](ai-redteam-scope.md).

## 11. Principles (stay aligned)

1. **Value over features.** A small PR that removes risk beats a big PR that
   adds surface area.
2. **Execute autonomously.** Don't ask permission for reversible changes; do
   ask before destructive or cross-cutting ones.
3. **No AI slop.** Every claim in a PR or doc must be verifiable from the
   diff or the data.
4. **Never reduce the test suite.** 1,967 passing today — your PR should leave
   it at ≥ 1,967.
5. **Go deep, not shallow.** Production-grade or don't ship.
