# Codex Megaprompt — Tranche 3 — Sapphire OS — 2026-04-28

> **Operator usage**: paste this entire document verbatim into a fresh Codex session. Codex MUST read top-to-bottom before any tool calls. The end of the document defines the closeout the operator expects on the next morning.

---

## 0. Mission

You are Codex, working overnight on the Sapphire OS monorepo at `~/Code/Sapphire` with **full autonomy granted by the operator (Ari)** for the duration of his sleep window. This is **Tranche 3** of a high-velocity multi-agent push:

- **Tranche 1** (Codex Agents A / B / C, 2026-04-28 morning): pytest collection restoration, repo hygiene, BacktestEngine adapter, sweep regen, performance endpoints, risk-kernel public-type coverage. **12 PRs merged.**
- **Tranche 2** (Claude Code night session + Codex 6-lane megaprompt, 2026-04-28 evening through ~05:00 UTC): Wave 4 acquisition surfaces (vertex eval, telegram operator-console hardening, threat-intel/customer-dossier dashboards, BQ vector retrieval mock + live, vertex gecko embedder, telegram channel intel reader read path, hyperliquid public feed, sovereign-thesis story page, /diligence aggregate page, routine_pause flag enforcement, dev_pulse + control-plane scoring date-flake fixes, dep vulns, isolated lib + plugin/lib + services test coverage, architecture-overview refresh, CODEOWNERS gate). **23 PRs merged.**

The mental model for **Tranche 3** is: *From Built to Bought*. Tranche 2 shipped capability; Tranche 3 makes Sapphire **demonstrably acquirer-ready**. A Palantir / Robinhood corp-dev reviewer should be able to walk into `~/Code/Sapphire` tomorrow morning, run two URLs in their browser (`/observability` and `/diligence`), read three docs (`docs/products/live-trading-ramp-memo.md`, `docs/security/kill-switch-invariants.md`, `docs/diligence/00-09`), and form a complete picture of what they'd be acquiring — capability, safety, durability, and the ramp from here to live capital — without asking the operator a single question.

If your runtime supports parallel sub-agents, dispatch the 8 lanes concurrently in worktrees. If not, do them sequentially in the order listed (highest-impact first).

---

## 1. Non-negotiable constraints

These bind every commit, every PR, every action. Two are NEW this tranche; pay attention:

1. **No-spend posture is sacred.** Every commit message ends with `[skip ci]`. Hosted GitHub Actions billing is gated by `vars.SAPPHIRE_RUNNER`; the local-CI runner is the merge gate. **NEW**: when admin-merging via `gh pr merge --squash`, you MUST pass `-t '<PR title> [skip ci]'` (or `--subject`) — the default behavior uses the PR title verbatim, which drops `[skip ci]`. Tranche 2 hit this on PR #388. The fix is documented in Lane 6 of this prompt; until then, ALWAYS supply `-t` explicitly. After every merge, run `gh run list --limit 5 --json databaseId,status` and cancel anything queued.
2. **Don't touch the trading critical path without operator confirmation.** That means: `services/alpha/`, `lib/portfolio/robinhood.py`, `lib/trading/`, `lib/analytics/risk_engine.py`, `lib/analytics/strategies.py`, `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`, `services/webhook/`, `contracts/`. CODEOWNERS already gates these. Do not author changes that need a review you cannot get.
3. **NEW: Watch for the fixture-clock vs impl-clock date-flake pattern.** Tranche 2 shipped two of these (#377 dev_pulse, #394 control-plane scoring) and they will keep showing up wherever a test builds a fixture timestamp from a fixed `NOW` constant but calls an impl that defaults to real `datetime.now()`. When you write or modify any test that uses `datetime.now()`, `date.today()`, or `time.time()`, ask: "if this test runs at 00:32 local on the next day, does the assertion still hold?" If not, monkey-patch the impl's clock with a `FrozenDatetime` subclass and pin the fixture to the same anchor. The canonical fix template is in `tests/unit/test_dev_pulse.py::test_collect_trading_status_reads_signals_and_portfolio` and `tests/unit/test_control_plane_scoring.py::test_score_news_now_defaults_to_current_time`.
4. **Do not touch satellite repos.** Sapphire monorepo only.
5. **Secrets are read-only and live-mode-only.** `~/.sapphire/secrets.env`, `~/.config/sapphire-secrets/`, and the LaunchAgent plists are only ever READ when an env-flag-gated live path triggers. They are never echoed, logged, or committed.
6. **Dry-run is the default for any new external-API surface.** Mirror `plugins/claw-sapphire/tools/internal/gemini_ooda.py`, `plugins/claw-sapphire/tools/internal/vertex_eval.py`, and `plugins/claw-sapphire/tools/internal/telegram_intel.py` — sensitivity gate, hard caps, secrets only loaded when the live env flag is set, cache + counters under `~/.cache/sapphire/<tool>/`.
7. **Provenance envelopes on all generated artifacts.** Use `lib/core/provenance.py`. Every emitted JSON deliverable gets a sibling `.envelope.json` with `{generator, model, prompt_hash, source_hashes, ttl, version}`.
8. **No README test counts during multi-lane work.** A single closeout PR (or in-place edit on the canonical handoff commit) updates `README.md` once at the end. Do not fight rebases.
9. **No new top-level dependencies** unless the lane explicitly authorizes them. Lane 4 is the only lane this tranche authorized to add a new prod dep (Playwright for the screenshot harness). Everything else is stdlib + already-pinned.
10. **Worktree-per-lane.** Each lane creates its own worktree at `/Users/aribs/Code/_worktrees/sapphire-<branch>`. Clean up worktrees when the lane's PR merges. Never commit directly to canonical `~/Code/Sapphire` for code; documentation-only direct pushes to main are allowed if scoped and `[skip ci]`.
11. **Open PR but DO NOT auto-merge** unless local verification is green: `ruff check .`, both pytest blocks (unit + plugin) — separately, never co-invoked, see §4 — `validate_tool_registry.py`, and `production_readiness_sweep.py --no-external` (which must report `0 FAIL`). If green, admin-squash-merge with `gh pr merge <N> --squash --admin --delete-branch -t "<commit subject> [skip ci]"`.
12. **Check for and merge stale recovery stashes from Tranche 2 before starting.** Tranche 2's parallel work created `backup/chore-move-pm-bot-token-tests-20260428T064418Z` plus archive at `/Users/aribs/Code/_worktree-archives/canonical-wip-20260428T064418Z/`. Inspect them and either (a) drop after confirming nothing is unique, or (b) preserve and document in your closeout. Same for any Codex / Claude stashes preserved in `git stash list`.

---

## 2. State at start

Re-verify these BEFORE dispatching any work. If any drift, stop and write a short report.

```bash
cd ~/Code/Sapphire
git fetch --all --quiet
git rev-parse --short HEAD               # expect: 4aed0382 (or a clean descendant)
gh pr list --state open                  # expect: empty (zero PRs open)
gh issue list --state open               # expect: 1 (informational #393, threat-intel sweep — leave alone unless an action lands)
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short        # expect: 4219 passed, 1 skipped, 21 xfailed
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q  # expect: 291 passed
/usr/local/bin/python3 scripts/validate_tool_registry.py          # expect: registry=42, errors=0
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -3   # expect: 0 FAIL
ls /Users/aribs/Code/_worktrees/                                  # expect: empty (all Tranche 2 worktrees cleaned)
git worktree list                                                 # expect: canonical only
```

Reference reading (skim before any lane):

- `docs/handoffs/codex-overnight-megaprompt-2026-04-28-report.md` — Tranche 2 closeout (THIS IS YOUR PREDECESSOR).
- `docs/handoffs/claude-night-session-2026-04-28-report.md` — Claude's Tranche 2 contribution.
- `docs/handoffs/codex-overnight-agent-A/B/C-2026-04-28-report.md` — Tranche 1.
- `docs/handoffs/codex-overnight-megaprompt-2026-04-28.md` — the previous megaprompt, structurally similar to this one.
- `CLAUDE.md` — repo-level conventions, paths, gotchas.
- `docs/architecture-overview.md` — current system map (refreshed in #381).
- `docs/products/*.md` — every Wave 4 + Tranche 2 product doc; this is what an acquirer reads first.
- `docs/diligence/00`–`09` — the diligence packet (PR #341).
- `infra/tool-registry.yaml` — 42 tool entries, source of truth.
- `plugins/claw-sapphire/tools/internal/{gemini_ooda,vertex_eval,telegram_intel,hyperliquid}.py` — canonical external-API tool templates; copy this shape for any new tool.

---

## 3. Lanes

Eight lanes. Each lands in a single PR — **do not bundle**. Order matters: higher-impact first, so if you must skip, skip from the bottom.

### LANE 1 — Sapphire Signal Correlation Engine (HIGHEST IMPACT — NEW SURFACE)

**Why it matters**: Tranche 2 shipped FIVE distinct signal feeds (TradingView webhooks, Telegram intel reader, Hyperliquid public feed, threat-intel sweep, sovereign-thesis convergence-watchlist). Each is independently valuable but the WHOLE is currently greater than the sum of the parts ONLY in the operator's head. This lane builds the engine that fuses them: cross-source correlation that emits a unified `edge_score` per `(symbol, timeframe)` along with a `corroborated_by` array naming each contributing source. **This is THE differentiator a buyer will recognize** — it transforms Sapphire from a portfolio of intel surfaces into a multi-modal alpha engine.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-signal-correlator` on `feat/signal-correlation-engine`.

**Templates to read first**:
- `lib/analytics/forecast.py` — existing reconciliation logic between Kronos OHLCV projections and TA scanner predictions; emits `consensus` (AGREE_BULL / AGREE_BEAR / CONTRADICT / etc.) and `edge_score`. Mirror the consensus vocabulary and extend to N-source.
- `lib/core/event_bus.py` — pub/sub primitive; the correlator subscribes to all signal topics and publishes a unified `signal.correlated` topic.
- `services/hyperliquid/src/hyperliquid_bot/public_feed.py` — example async subscriber.
- `lib/intel/sovereign_thesis.py` and `lib/intel/bq_vector_store.py` — source-snapshot patterns.

**Files**:
- `lib/correlator/__init__.py`
- `lib/correlator/engine.py` (~600 LOC) — pure logic: takes a dict of `{source_name: latest_signal}` for a `(symbol, timeframe)` and returns a `CorrelatedSignal` dataclass with `edge_score: float ∈ [-1, +1]`, `consensus: Literal[...]`, `corroborated_by: list[str]`, `divergent_sources: list[str]`, `freshness_seconds: float`, `provenance_envelope: dict`. NO I/O at module load. Reads no env vars.
- `lib/correlator/sources.py` (~300 LOC) — adapters for each upstream feed: `TradingViewSource`, `TelegramIntelSource`, `HyperliquidSource`, `ThreatIntelSource`, `ConvergenceWatchlistSource`, `SovereignThesisSource`, `KronosForecastSource`, `TAScannerSource`. Each adapter exposes `latest_for(symbol, timeframe) -> SourceSignal | None`. All read from `data/` snapshots — no network.
- `lib/correlator/scoring.py` (~200 LOC) — pure scoring: weights per source, freshness decay, agreement bonuses, contradict penalties, all overrideable via config.
- `services/correlator/run.py` (~250 LOC) — async daemon that polls all sources every N seconds (config), runs the engine, publishes to event bus, writes `data/correlated_signals/<date>/signals.jsonl` with provenance envelopes.
- `services/correlator/launchagent/com.sapphire.signal-correlator.plist.template`.
- `plugins/claw-sapphire/tools/internal/signal_correlator.py` (~350 LOC) — stdin-JSON tool. Actions: `correlate-once`, `latest`, `status`, `weights`. Mirrors `gemini_ooda` shape.
- `plugins/claw-sapphire/tools/signal_correlator.py` — 3-line shim.
- `tests/unit/test_correlator_engine.py` (≥ 25 cases): fully agree, fully contradict, partial agreement, freshness decay edge cases, divergent-source isolation, weight-zero source ignored, single-source no-bonus, idempotence (same input → same output across 100 runs).
- `tests/unit/test_correlator_sources.py` (≥ 18 cases): one per source adapter, all I/O mocked.
- `tests/unit/test_correlator_scoring.py` (≥ 12 cases): pure scoring math. Property tests for monotonicity and bound.
- `services/correlator/tests/test_correlator_run.py` (≥ 8 cases) OR `tests/unit/test_correlator_run.py` if it slots there.
- `plugins/claw-sapphire/tests/test_signal_correlator.py` (≥ 10 plugin tests).
- `infra/tool-registry.yaml` — append `signal_correlator` under "AI complement" or new "Signals" section.
- `docs/products/signal-correlator-0.1.0.md` (1200+ words) — buyer-facing capability doc. Walk through a worked example: BTC bullish from TradingView, bullish from Telegram intel @glassnode, neutral from Hyperliquid, bullish from convergence-watchlist → `edge_score = 0.78, consensus = AGREE_BULL_4_OF_5`.
- `docs/ops/signal-correlator-runbook.md` (1500+ words).

**Caps**:
- `MAX_SOURCES_PER_CORRELATION = 16`
- `MAX_CORRELATIONS_PER_HOUR = 1200`
- `FRESHNESS_HARD_LIMIT_SECONDS = 86400`
- `EDGE_SCORE_BOUND = (-1.0, +1.0)` enforced at output

**Constraints**:
- **Read-only signal consumer**. The correlator NEVER writes back to source streams.
- **No live trading**. Output is signal/intel-only; downstream consumers (paper trader, dashboards) decide what to do.
- **Provenance envelope** on every `data/correlated_signals/<date>/signals.jsonl` daily file.
- The engine MUST be tunable via `~/.sapphire/correlator_weights.yaml` with documented defaults; missing config falls back to sane defaults.

**PR title**: `feat(signals): cross-source signal correlation engine 0.1.0`

---

### LANE 2 — Real-time Observability Dashboard (`/observability`)

**Why it matters**: Sapphire now has 19 services, 23 LaunchAgents, 5+ signal streams, and 4-tier inference routing. There is no single page that shows the LIVE state of all of it. An operator (and an acquirer's lead engineer) needs single-pane-of-glass observability. This lane builds it.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-observability-dashboard` on `feat/observability-dashboard`.

**Templates to read first**:
- `services/dashboard/templates/pages/diligence.html` (PR #386) — the most recent dashboard page; same pattern.
- `services/dashboard/app.py` — route + auth setup.
- `plugins/claw-sapphire/tools/internal/health_check.py` — 20-point health surface.
- `plugins/claw-sapphire/tools/internal/dev_pulse.py` — cross-repo dev pulse, also surfaces LaunchAgent + service state.
- `plugins/claw-sapphire/tools/internal/service_supervisor.py` — supervisor view.

**Files**:
- `services/dashboard/templates/pages/observability.html` — the page. Sections: System Heartbeat (uptime, last-fire times for all 23 LaunchAgents), Inference Proxy (4-tier health + token consumption + per-tier latency), Signal Streams (TradingView / Telegram intel / Hyperliquid / threat-intel / convergence-watchlist rates), Provenance Coverage (envelopes_total, missing_or_invalid, last_verify_at), Routine Pause Status (which routines are paused with timestamps), Event Bus (last N events from `data/events/bus.jsonl` with topic distribution).
- `services/dashboard/app.py` — add the `/observability` route (auth-inherited) plus three NEW lightweight read-only API endpoints:
  - `/api/observability-system-summary` — JSON of the full state above.
  - `/api/observability-stream-rates` — per-source signal rates (last 1h, 24h).
  - `/api/observability-launchagents` — labels, last_exit, restart_count, last_fired_at.
- `lib/observability/__init__.py` and `lib/observability/aggregator.py` (~400 LOC) — pure logic: takes inputs from disk + `launchctl list` (subprocess) and returns a single `SystemSnapshot` dataclass.
- `tests/unit/test_observability_aggregator.py` (≥ 15 cases). Mock all subprocess + filesystem I/O.
- `tests/unit/test_dashboard_observability_routes.py` (≥ 10 cases).
- `docs/ops/observability-dashboard-runbook.md` (700+ words).

**Constraints**:
- **Read-only HTTP**. GET only.
- **Auth inherited**. Do not weaken.
- **No new external deps** (no Prometheus client, no Grafana). Pure Flask + Jinja + SVG charts.
- **No live network calls** in tests; use Flask test client and mocked subprocess.
- **Refresh interval**: page polls APIs every 15s client-side. Server is stateless.
- **No secrets in output** — apply `lib/security/pii_redactor.py` if any field could leak.

**PR title**: `feat(dashboard): real-time observability page`

---

### LANE 3 — Foundry Ontology Expansion

**Why it matters**: `lib/foundry/sdk.py` ships a versioned envelope and `lib/foundry/sync.py` is the daemon that pushes Sapphire entities into Palantir Foundry. Tranche 2 added FIVE new ontology-worthy objects (`IntelVectorRecord`, `TelegramIntelMessage`, `HyperliquidSignal`, `OODAPacket`, `ThreatIndicator`) but none of them flow into Foundry yet. This lane wires them in. The acquisition pitch hinges on "Sapphire's intel surfaces are machine-discoverable inside Foundry" — without this, the pitch is aspirational.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-foundry-ontology-expansion` on `feat/foundry-ontology-expansion`.

**Templates to read first**:
- `lib/foundry/sdk.py` — envelope + idempotency ledger + replay.
- `lib/foundry/ingestion.py` — local → ontology-object transform.
- `lib/foundry/sync.py` — 15-min delta-aware daemon.
- `docs/foundry-ontology-schema.md` — current schema + naming conventions.
- The 5 source files: `lib/intel/bq_vector_store.py` (IntelVectorRecord), `services/telegram_intel/sink.py` (TelegramIntelMessage), `services/hyperliquid/src/hyperliquid_bot/public_feed.py` (HyperliquidSignal), `plugins/claw-sapphire/tools/internal/gemini_ooda.py` (OODAPacket), `plugins/claw-sapphire/tools/internal/threat_intel.py` (ThreatIndicator).

**Files**:
- `lib/foundry/ingestion.py` — extend with 5 new transforms. Each transform: `to_<TypeName>(record: <SourceType>) -> dict` returning a Foundry-ready dict with the standard envelope.
- `lib/foundry/sync.py` — register the 5 new types with the delta-aware sync loop. Each gets its own `last_synced_at` watermark file under `~/.cache/sapphire/foundry_sync/<type>.json`.
- `docs/foundry-ontology-schema.md` — extend with the 5 schemas (each: type name, field table, indexed fields, retention).
- `tests/unit/test_foundry_ingestion_extensions.py` (≥ 30 cases): ≥ 5 cases per type covering envelope shape, watermark progression, delta detection, malformed-source rejection, retry logic on transient errors.
- `tests/unit/test_foundry_sync_extensions.py` (≥ 15 cases).
- `docs/products/foundry-ontology-0.2.0.md` — bump the doc to 0.2.0 with the expanded surface.

**Constraints**:
- **Live Foundry calls remain operator-gated** by the existing `SAPPHIRE_FOUNDRY_LIVE=1` flag. Tests mock the Foundry client.
- **Backward compatible**: existing types must continue to sync unchanged.
- **Idempotency ledger** must absorb the new types — same key uniqueness rules.

**PR title**: `feat(foundry): expand ontology with 5 new tranche-2 surfaces`

---

### LANE 4 — Acquirer Microsite + Diligence-page Polish (Playwright Screenshots)

**Why it matters**: The `/diligence` and `/sovereign-thesis-story` pages exist (PR #386) but have not been visually validated, copy-edited, or screenshotted. The diligence packet docs (`00–09`) are markdown-only — there's no public-facing surface. This lane closes both gaps: a static acquirer microsite at `web/acquirer/` AND Playwright-driven screenshot regression for the dashboard pages.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-acquirer-microsite` on `feat/acquirer-microsite-and-screenshots`.

**Files**:
- `web/acquirer/index.html` — single-page static HTML/CSS site (NO JS framework, no build step). Sections: Mission (1 paragraph), Capabilities (the 8 Wave-4 surfaces as cards with sparkline metrics and screenshots), Tech Stack (Mac/Windows/Pi mesh, 4-tier inference, contracts), Diligence Packet (links to `docs/diligence/00–09`), Safety Posture (kill-switch, confirmation firewall, provenance envelopes), Founders + Contact.
- `web/acquirer/assets/styles.css` — Tailwind-via-CDN OR vanilla CSS (your call — prefer vanilla for portability).
- `web/acquirer/assets/screenshots/` — placeholder PNG names; populated by Lane 4's screenshot harness.
- `scripts/ops/render_acquirer_screenshots.py` — Playwright harness. Boots the dashboard locally on a temp port (test-client style), navigates to each authenticated page (`/`, `/sovereign-thesis`, `/threat-intel`, `/customer-dossier`, `/diligence`, `/sovereign-thesis-story`, `/observability` once Lane 2 lands), captures full-page PNG. Refuses to run unless `SAPPHIRE_PLAYWRIGHT_LOCAL=1` is set so it never auto-fires in CI.
- `web/acquirer/requirements.txt` — `playwright>=1.44,<2.0`. **NEW prod dep authorized for THIS lane only.** Document install in the runbook.
- `tests/unit/test_acquirer_microsite_html.py` (≥ 12 cases) — pure HTML structure validation: every link target exists, every screenshot reference has a placeholder, no inline JS, no external resource loads outside `assets/`.
- `tests/unit/test_render_acquirer_screenshots_dryrun.py` (≥ 6 cases) — verify the harness's dry-run mode (no Playwright import in dry-run path), env-flag gating, output-dir creation, idempotent re-runs.
- `docs/ops/acquirer-microsite-runbook.md` (1000+ words) — how to render screenshots, how to host the site (instructions for `python3 -m http.server` from `web/acquirer/` AND for Cloudflare Pages / Netlify deploy).
- `docs/products/acquirer-microsite-0.1.0.md` — short, links to live site + diligence packet.

**Constraints**:
- **Static site only**. No backend.
- **No tracking pixels, no analytics, no external JS.** Self-contained.
- **Screenshot harness is operator-driven**. Tests verify the dry-run path; live Playwright runs are operator-gated.
- **No real screenshots committed** until the operator runs the harness. Commit empty placeholders + `.gitkeep`.
- **Playwright install instructions** must include `python3 -m playwright install chromium` and be explicit about size (~300 MB).

**PR title**: `feat(acquirer): static acquirer microsite + dashboard screenshot harness`

---

### LANE 5 — Live-trading Ramp Memo + Kill-switch Invariants Doc

**Why it matters**: Two operator-readable, buyer-readable diligence-grade docs that the operator's memory currently holds in his head. Without them on disk, an acquirer's CTO has to ask the operator "what's your path to live capital?" and "what stops a bad trade from ruining the firm?" — and getting those answers in conversation is much weaker than reading them on disk. This lane writes both.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-trading-ramp-doc` on `docs/trading-ramp-and-kill-switch`.

**Files**:
- `docs/products/live-trading-ramp-memo.md` (3000+ words) — the canonical operator-and-buyer-readable memo. Sections:
  1. **Current state**: paper-only, $5/$50 manual confirmation cap (per `project_robinhood_live_capital_posture.md`), crypto-only.
  2. **Phase 0 → 1: Paper expansion** — what would un-pause autonomous paper trading for stocks. Gates: prediction accuracy floor (BTC 75%+, ETH 60%+, SOL 60%+ for 30 days). Rollback: instantly to paper-only.
  3. **Phase 1 → 2: Crypto live tier** — $5 → $50 → $500 ramp with metric gates. Sortino > 1.5 for 14 trading days at each rung.
  4. **Phase 2 → 3: Stock live tier** — separate broker integration; not yet started; what the gates would look like.
  5. **Kill switches and rollbacks** — every switch and every rollback path enumerated with confirmation procedures.
  6. **Open questions and assumed gates** — be honest about what's still TBD.
  7. **Acquirer relevance** — explicit note: "this memo articulates the regulated ramp from paper to live. A buyer absorbing Sapphire would inherit this gating; do NOT skip phases."
- `docs/security/kill-switch-invariants.md` (2500+ words) — every kill switch enumerated. Sections:
  1. **Layer 1 — Trade-time invariants** (in `lib/core/risk_kernel.py`, `lib/core/circuit_breaker.py`): drawdown threshold, consecutive-loss threshold, latency threshold, position-size cap, idempotency.
  2. **Layer 2 — Confirmation firewall** (`lib/core/confirmation_firewall.py`): two-phase commit on destructive actions, expiration, archive flow.
  3. **Layer 3 — Operator manual halt** (Telegram operator console, `/cancel-routine`, `/routines pause`, dashboard kill switch).
  4. **Layer 4 — Heartbeat + supervisor** (60s heartbeat state machine, `service_supervisor` LaunchAgent restart cap).
  5. **Recovery paths**: how each kill is reset.
  6. **Witness**: every kill emits an event on the event bus with structured metadata; every reset is logged.
  7. **Test coverage map**: link each invariant to its test file.
- `docs/products/live-trading-ramp-memo.envelope.json` and `docs/security/kill-switch-invariants.envelope.json` — provenance envelopes for both.
- `tests/unit/test_kill_switch_invariants_doc.py` (≥ 8 cases) — sanity tests that the doc references real files: every `lib/core/...` reference must point to a real symbol; every test-file reference must exist.

**Constraints**:
- **No code changes** — these are docs.
- **Honest gating** — if a phase or invariant doesn't actually exist yet, say so explicitly. Do NOT fabricate confidence.
- **Provenance-stamped** so a buyer can verify these docs match the codebase as of a specific SHA.
- **Operator-readable AND buyer-readable**: skim-friendly headers, no internal-only jargon.

**PR title**: `docs(security): live-trading ramp memo + kill-switch invariants`

---

### LANE 6 — Routine-pause Status Surface + Safe-merge Guardrail

**Why it matters**: Combines two backlog items from Tranche 2's closeout (items 1 + 5):
- **Backlog 5**: paused routines are currently invisible — operator runs `/routines pause foo` but no UI shows what's paused.
- **Backlog 1**: PR #388's squash subject dropped `[skip ci]` because `gh pr merge --squash` uses the PR title verbatim. We need a guardrail.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-pause-and-merge-guardrail` on `feat/pause-status-and-merge-guardrail`.

**Files**:
- `plugins/claw-sapphire/tools/internal/sapphire_pm_bot.py` — extend `/routines list` to include a "(paused)" tag for each routine whose flag exists in `~/.sapphire/routine_pause/`. Add a new `/routines status` command that returns ONLY the paused list with timestamps.
- `services/dashboard/app.py` + `services/dashboard/templates/pages/observability.html` (Lane 2 must land first; if not, this section adds it) — paused-routines section.
- `scripts/ops/sapphire_safe_merge.sh` — guardrail wrapper. Usage: `sapphire-safe-merge <PR>`. Calls `gh pr view`, extracts the title, ensures `[skip ci]` is appended, then calls `gh pr merge $PR --squash --admin --delete-branch -t "<title> [skip ci]"`. After merge, runs `gh run list --limit 5 --json databaseId,status` and cancels anything in `queued` or `in_progress`.
- `scripts/ops/sapphire_safe_merge.py` — Python equivalent, importable from tests.
- `tests/unit/test_sapphire_safe_merge.py` (≥ 12 cases) — mock `gh` subprocess entirely. Verify: subject append, idempotent (already-has-`[skip ci]` not double-appended), cancel-queued logic, error path on bad PR number.
- `plugins/claw-sapphire/tests/test_sapphire_pm_bot.py` — extend with ≥ 6 cases for the routines-list-paused-tag behavior and `/routines status`.
- `docs/ops/safe-merge-runbook.md` (700+ words).
- `Makefile` — add `make safe-merge PR=<N>` target wrapping the script.

**Constraints**:
- **No fundamental change to `_telegram_safety` or PM bot allowlist** — extend, don't refactor.
- **Backward compat**: existing `/routines pause / resume / list` commands keep working.
- **CODEOWNERS gate**: any change to `_telegram_safety.py` or `sapphire_pm_bot.py` requires `@arigatoexpress` review (already gated in #379).
- **Cancel-queued logic must be safe**: check the runs are FOR THE PR JUST MERGED, not arbitrary fleet runs.

**PR title**: `feat(ops): routine-pause status surface + safe-merge guardrail`

---

### LANE 7 — Customer Dossier 0.2.0 + Dependabot tooling gap

**Why it matters**: PR #374 flagged "per-tenant hash salt + cell-suppression for small-status counts" as a 0.2.0 follow-up. Issue #393 noted that Dependabot alerts API was unreachable via current tooling. This lane closes both.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-dossier-and-deps` on `feat/dossier-0.2.0-and-deps-tooling`.

**Files**:
- `lib/security/pii_redactor.py` — extend with a `per_tenant_hash(value: str, tenant_id: str) -> str` function that uses HMAC-SHA256 with a per-tenant salt loaded from `~/.sapphire/secrets.env` (`SAPPHIRE_DOSSIER_HASH_SALT_<TENANT_ID>`). Falls back to a deterministic-but-randomized default in non-live mode.
- `services/dashboard/app.py` — `/customer-dossier` route honors the per-tenant hash AND applies cell-suppression: any status bucket with count < 5 gets reported as `<5` instead of the exact number.
- `tests/unit/test_pii_redactor_per_tenant_hash.py` (≥ 12 cases): determinism per `(value, tenant)`, isolation (different tenant → different hash), salt-missing fallback, salt-rotation invalidation.
- `tests/unit/test_dashboard_customer_dossier_v2.py` (≥ 10 cases): cell-suppression triggers on small buckets, exact counts on large buckets, hash visible but raw PII still absent.
- `scripts/ops/dependabot_alerts_fetch.py` — fetch via `gh api repos/arigatoexpress/Sapphire/dependabot/alerts?state=open` with token validation, output paste-safe summary; emits a structured JSON. Replaces the gap noted in issue #393.
- `tests/unit/test_dependabot_alerts_fetch.py` (≥ 8 cases) — mock `gh api` subprocess.
- `docs/products/customer-dossier-0.2.0.md` — bump doc to 0.2.0.
- `docs/ops/threat-intel-sweep-runbook.md` — extend with a section on running the dependabot fetcher.

**Constraints**:
- **Backward compat with 0.1.0**: a tenant without a configured salt continues to get the deterministic-default hash; no breaking change.
- **Dependabot fetcher is read-only**.

**PR title**: `feat(security): customer-dossier 0.2.0 + dependabot fetcher`

---

### LANE 8 — Reusable Health-Context Helper

**Why it matters**: Backlog item 7 from Tranche 2 closeout. The Nemotron Telegram fix (#383) built a live health-context summary inline. The same logic is reimplemented across `health_check`, `dev_pulse`, `morning_digest`, and now the observability dashboard (Lane 2). Centralize it.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-health-context-helper` on `feat/health-context-helper`.

**Files**:
- `lib/agents/health_context.py` (~250 LOC) — `build_health_context(scope: Literal["telegram", "morning", "ops", "minimal"]) -> HealthContext` returning a structured snapshot. Pure, no I/O at module load. Accepts an optional `clock` callable for testability.
- `services/telegram-bot/app.py` — replace the inline summary builder with a call to `build_health_context("telegram")`.
- `plugins/claw-sapphire/tools/internal/morning_digest.py` — same.
- `plugins/claw-sapphire/tools/internal/dev_pulse.py` — replace any inline health summary with the helper where appropriate (preserve existing `dev_pulse` JSON contract).
- `services/dashboard/app.py` — `/api/observability-system-summary` (Lane 2) calls the helper.
- `tests/unit/test_health_context_helper.py` (≥ 18 cases): each scope variant, time-frozen via injected clock, error path on missing data.

**Constraints**:
- **No behavior changes** to the existing surfaces. The helper produces output IDENTICAL to what was previously inlined. Add deprecation warnings on the old inline paths if any remain.
- **Inject clock for testability** — the helper takes an optional `now: Callable[[], datetime]` so tests can pin it.

**PR title**: `refactor(agents): reusable health-context helper`

---

## 4. Verification protocol (every lane)

Before opening a PR, get all six green from inside the worktree:

```bash
ruff check .
/usr/local/bin/python3 -m pytest <NEW_TEST_FILES> -q --tb=short
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

Readiness MUST report `0 FAIL`. WARNs may stay. **Run `tests/unit/` and `plugins/claw-sapphire/tests/` SEPARATELY** — pytest cannot load both conftest.py files in the same invocation.

When canonical pytest crosses local midnight, **watch for fixture-clock-vs-impl-clock date flakes**. The two known cases (#377, #394) are documented; any new failure that disappears on re-run is your hint to apply the FrozenDatetime template.

---

## 5. PR template

Each PR body must include:
- **What this enables** — acquisition-grade framing.
- **Safety posture** — env gates, caps, no secrets at rest.
- **Local verification** with the six command outputs (or trimmed tails).
- **Files changed** with the file list.
- **Follow-ups not in this PR** — be honest about what you deferred.

End with `🤖 Generated with [Claude Code](https://claude.com/claude-code)` ONLY if Codex's runtime emits that footer; otherwise omit.

---

## 6. Merge protocol (UPDATED — read carefully, this fixed Tranche 2's bug)

When local verification is green and `gh pr view <N>` shows `mergeStateStatus: CLEAN, mergeable: MERGEABLE`:

```bash
git -C ~/Code/Sapphire worktree remove /Users/aribs/Code/_worktrees/sapphire-<branch> --force

# Get the title and ALWAYS append [skip ci] explicitly
TITLE=$(gh pr view <N> --json title --jq '.title')
SUBJECT="${TITLE} [skip ci]"

gh -R arigatoexpress/Sapphire pr merge <N> --squash --admin --delete-branch -t "$SUBJECT"

git -C ~/Code/Sapphire pull --quiet

# Cancel any queued / in-progress hosted runs that the merge may have triggered
gh run list --limit 5 --json databaseId,status,headSha --jq '.[] | select(.status=="queued" or .status=="in_progress")'
# If any results, cancel:  gh run cancel <id>
```

**OR** use the new `scripts/ops/sapphire_safe_merge.sh` from Lane 6 once that lane lands — it does all of this for you.

If a registry-yaml conflict appears between two lanes: rebase the second lane on top of the merged first, regenerate the registry append, re-run verification, push.

---

## 7. Closeout deliverable

After the last lane merges, write **one** handoff doc at `docs/handoffs/codex-megaprompt-tranche-3-2026-04-29-report.md` and commit it directly to main with `[skip ci]`. The doc MUST include:

1. **Final main SHA** + open PR/issue counts.
2. **Per-lane status table** — lane name, PR number, files changed, test delta, key design decisions, caveats.
3. **Verification at handoff** — the six commands' tail output.
4. **Operator-owed actions** — anything the operator needs to do.
5. **Skipped lanes (if any)** with one paragraph per skip.
6. **Next-tranche backlog** — what should Tranche 4 tackle.
7. **NEW: Squash-merge subject audit** — confirm every Tranche 3 squash subject ended with `[skip ci]`. If any didn't, list them and the cancellation evidence for any queued runs.

Then update `~/.claude/projects/-Users-aribs/memory/MEMORY.md` (one line in the index pointing to a new file at `~/.claude/projects/-Users-aribs/memory/project_2026-04-29_codex_tranche_3.md`).

---

## 8. Posture reminders

- **Acquisition-grade**: a Palantir/Robinhood corp-dev reviewer is your primary audience. Every doc, every dashboard, every test report should be coherent to a smart skim-reader who has never seen the codebase.
- **Honesty over hype**: if a lane hits a real blocker, write a 1-paragraph "discovered but not fixed" entry and move on. Never fake a green build.
- **Provenance is non-negotiable**.
- **Trading critical path is sacred**.
- **Respect the operator's time**: a 10-minute morning review should let him approve everything OR surgically revert one lane. Per-lane PRs make that possible.
- **The fixture-clock date flake will keep happening**: scan every new test you write for it. The pattern is so common at this scale that prevention beats cure.

This is the third tranche of a multi-tranche acquisition push. Tonight's work, layered on top of Tranche 1 + Tranche 2, lands Sapphire as a defensible, auditable, buyer-readable system.

Now go.
