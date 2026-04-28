# Codex Megaprompt — Tranche 5 — The Compound Edge — 2026-04-29

> **Operator usage**: paste this entire document into a fresh Codex session. Codex MUST read top-to-bottom before any tool calls. The end of the document defines the closeout the operator expects.

---

## 0. Mission

You are Codex, operating with **full autonomy granted by the operator (Ari)** for a deep multi-hour tranche. This is **Tranche 5** in a multi-tranche acquisition push:

- **Tranche 1** (2026-04-28 morning): pytest collection, repo hygiene, BacktestEngine adapter — 12 PRs.
- **Tranche 2** (2026-04-28 evening): Wave 4 acquisition surfaces — 23 PRs.
- **Tranche 3** + supplement + fill-in (2026-04-28 night through 2026-04-29 morning): correlation engine, observability dashboard, Foundry ontology, acquirer microsite, ramp memo, safe-merge guardrail, dossier 0.2.0, health-context helper — ~14 PRs across the original lanes + Claude's 6 fill-in lanes.
- **Tranche 4** (2026-04-29): narrative synthesis, cross-asset regime, macro intel, on-chain depth, event-impact, counter-party intel, adversarial defense, competitive memo, integration pass — 9 PRs + production-readiness sprint follow-on.
- **Production-readiness sprint** (Days 3-7 audit): branch protection, secrets matrix, rollback runbook, observability warnings, closeout — multiple support PRs.
- **Claude meantime tranche** (2026-04-29 afternoon): playbook, pitch deck, comms templates, brand assets — 4 PRs.
- **Tranche 5** (NOW — this prompt): the compound layer. Tranche 4 wired the intelligence surfaces. **Tranche 5 makes them self-verifying, customer-facing, and production-deployable.**

Mental model: **The Compound Edge.** Tranche 4 built capability that operates in dry-run / paper / mock-default postures. Tranche 5 turns that capability into:

1. **Self-verifying systems** — Sapphire watching Sapphire (audit panel, narrative self-eval).
2. **Customer-facing surfaces** — pivot from internal tooling to potential B2B revenue (customer API, pricing tiers, public demo).
3. **Production-deployable** — `make sapphire-on-fresh-mac` actually works; a buyer can spin it up.
4. **Live capital integrated** — the $5 BTC fill stops being a memory note and becomes a structured ledger entry that the dashboard, ramp gate, and audit panel all consume.

A Palantir / Robinhood corp-dev reviewer should be able to (a) spin up Sapphire on their laptop using the reproducibility playbook, (b) see the live capital ledger with first $5 fill, (c) read the audit panel report showing what autonomous agents have shipped + how the system audits itself, (d) consume sample customer API output, and (e) hold a Pine strategy in TradingView that was generated from a Sapphire backtest winner. **All five of those would be impossible with what shipped through Tranche 4.** All five become reality with Tranche 5.

This is **deep work**. Lanes are bigger than Tranche 4. Quality over speed. **A polished single deliverable per lane is worth more than three shallow ones**. If you must skip a lane, skip from the bottom.

If your runtime supports parallel sub-agents, dispatch all 9 lanes concurrently. If not, do them sequentially in the order listed.

---

## 1. Non-negotiable constraints

1. **No-spend posture is sacred.** Every commit ends with `[skip ci]`. Every `gh pr merge --squash` MUST pass `-t '<title> [skip ci]'` explicitly (or use `scripts/ops/sapphire_safe_merge.sh`). After every merge, run `gh run list --limit 5` and cancel anything queued.
2. **Don't touch the trading critical path** without operator confirmation: `services/alpha/`, `lib/portfolio/robinhood.py`, `lib/trading/`, `lib/analytics/risk_engine.py`, `lib/analytics/strategies.py`, `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`, `services/webhook/`, `contracts/`. Lane 1 (Live Capital Ledger) is allowed to ADD a NEW `lib/live_portfolio/` module that READS Robinhood data via existing operator-supervised paths, but does NOT modify the critical-path files themselves.
3. **Stay out of prior tranches' surfaces** for modification. ADD new modules; do not refactor `lib/correlator/`, `lib/synthesis/`, `lib/cross_asset/`, `lib/macro/`, `lib/event_impact/`, `lib/counterparty/`, `lib/security/adversarial_detectors.py`, `lib/observability/`, `lib/agents/health_context.py`, `lib/intelligence/tranche4_integration.py`. Lane 9 (integration) MAY make additive imports / wiring.
4. **The fixture-clock vs impl-clock date-flake template** still applies — three known cases now (#377, #394, plus any from production-readiness sprint). Anytime a test uses `datetime.now()` against an impl that takes a `now` arg, monkey-patch with the FrozenDatetime template.
5. **Web research lanes (Lane 5 partially, Lane 6 partially)**: cite primary URLs with retrieval dates. NEVER fabricate quotes / statistics.
6. **Do not touch satellite repos** (`Project-Go-Forward`, `regional-intel-workbench`, `cyber-threat-bot`, `Cointracker`, `hermes-agent`, `claw-code`, `tradingview-mcp-v2`).
7. **Secrets are read-only and live-mode-only.** Mirror `gemini_ooda` / `vertex_eval` / `narrative_synthesis` patterns: secrets only loaded when env-flag-gated live path triggers. Never logged.
8. **Dry-run is the default for any new external-API surface.** Caps + counters under `~/.cache/sapphire/<tool>/`.
9. **Provenance envelopes on all generated artifacts.** `lib/core/provenance.py`.
10. **No README test counts during multi-lane work.** Single closeout pass updates README.
11. **Worktree-per-lane.** `~/Code/_worktrees/sapphire-<branch>`. Clean up when PR merges. Never edit canonical for parallel work.
12. **Open PR but DO NOT auto-merge** unless local verification is green: ruff, both pytest blocks (separately, never co-invoked), `validate_tool_registry.py`, `production_readiness_sweep.py --no-external` (`0 FAIL`). When green, admin-squash-merge with explicit `-t`.
13. **Lane 1 + Lane 7 NEW**: anything that touches live-capital flows or customer-facing surfaces MUST stay paper / dry-run / mock-default until the operator flips an env flag in writing. Customer API DOES NOT charge real money; it returns sample data with a `mock=true` field unless `SAPPHIRE_CUSTOMER_API_LIVE=1` is set AND payment infrastructure is verified.
14. **Lane 6 NEW**: the reproducibility playbook MUST work on a fresh macOS without operator credentials. "Demo mode" is the default; live mode requires the operator to populate `~/.sapphire/secrets.env` and flip env flags.

---

## 2. Pre-flight + state at start

**BEFORE anything else**, verify Tranche 4 + production-readiness sprint + Claude meantime tranche all landed.

```bash
cd ~/Code/Sapphire
git fetch --all --quiet
git rev-parse --short HEAD                    # expect 180c3e72 or descendant
gh pr list --state open --json number          # expect 1: only #425 (operator-review pending)
gh issue list --state open --json number       # expect 1: only #393 (informational)
/usr/local/bin/python3 -m pytest tests/unit/ -q                 # expect ≥ 5,300 passed
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q   # expect ≥ 376 passed
/usr/local/bin/python3 scripts/validate_tool_registry.py        # expect registry ≥ 49, errors=0
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -3   # expect 0 FAIL
ls /Users/aribs/Code/_worktrees/                                 # expect: only sapphire-operator-comms (preserved per #425)

# Confirm Tranche 4 + Claude meantime surfaces exist
ls lib/correlator/ lib/synthesis/ lib/cross_asset/ lib/macro/ lib/event_impact/ lib/counterparty/ lib/intelligence/   2>&1
ls lib/observability/ lib/agents/health_context.py                                                                     2>&1
ls web/acquirer/assets/branding/                                                                                       2>&1
ls docs/diligence/sapphire-pitch-deck-2026-04-29.pptx                                                                  2>&1
ls docs/process/claude-force-multiplier-playbook-2026-04-29.md                                                         2>&1
ls docs/competitive/landscape-2026-04-28.md                                                                            2>&1
ls scripts/ops/sapphire_safe_merge.sh                                                                                  2>&1
```

If any deliverable is missing, **stop and write a pre-flight gap report**.

**Reference reading** (skim BEFORE any lane):
- `docs/handoffs/codex-megaprompt-tranche-4-2026-04-29-report.md`
- `docs/handoffs/codex-megaprompt-tranche-3-2026-04-29-report.md` (or whatever Tranche 3 closeout is named)
- `docs/process/claude-force-multiplier-playbook-2026-04-29.md` — strong signal for what Claude is uniquely positioned for, which informs which lanes are Codex-shaped vs Claude-shaped
- `docs/competitive/landscape-2026-04-28.md` — competitive context informs Lane 7 (customer surface)
- `docs/products/live-trading-ramp-memo.md` — Lane 1 builds on this
- `docs/security/kill-switch-invariants.md` — Lane 1 must respect every layer
- `docs/security/adversarial-intelligence-threat-model-2026-04-28.md` — Lane 2 builds on this
- `~/.claude/projects/-Users-aribs/memory/project_robinhood_first_live_trade_2026-04-28.md` — the canonical fact about the $5 fill that Lane 1 imports
- `CLAUDE.md` — live counts; should show 5,366+ tests, 49+ tools, 21+ scheduled tasks

---

## 3. Lanes

**Nine lanes (8 build + 1 integration pass).** Order matters: highest-impact first. Each lane is a single PR — DO NOT bundle.

---

### LANE 1 — Live Capital Ledger + Ramp Gate Engine (HIGHEST IMPACT — bridges paper to live)

**Why it matters**: The 2026-04-28 04:06 UTC $5 BTC limit-buy filled at $76,774.81 on account ...5966. That's a real fact, sitting in operator memory + Gmail confirmation. **It is NOT in the repo as a structured artifact.** The pitch deck slide 9 had to frame it as "designed and gated" instead of "executed" because no on-disk evidence exists. This lane fixes that by building a **live capital ledger** that the operator seeds with the $5 fill, computes the 14-day Sortino soak, and emits a `ramp.gate.satisfied` event when the $50 rung's gates are met.

This is THE bridge from paper-only to truly-live. After this lane, the dashboard `/observability` panel shows real fills, the audit panel (Lane 2) sees ramp progression, and the customer surface (Lane 7) can gate features by ramp tier.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-live-capital-ledger` on `feat/live-capital-ledger-and-ramp-gate`.

**Templates to read first**:
- `docs/products/live-trading-ramp-memo.md` — the canonical ramp framing.
- `docs/security/kill-switch-invariants.md` — every kill-switch layer this lane must respect.
- `lib/portfolio/robinhood.py` (DO NOT MODIFY) — read shape of `LiveTradeRecord` if exists; otherwise this lane defines it.
- `lib/analytics/strategy_performance.py` — Sortino computation pattern.
- `lib/core/provenance.py` — envelope.

**Files**:
- `lib/live_portfolio/__init__.py`
- `lib/live_portfolio/ledger.py` (~500 LOC) — pure: `LiveTradeRecord` dataclass (account, exchange, symbol, side, type, quantity, fill_price, fill_at, notional, fee, total_cost, ramp_tier, source_email_message_id_redacted, provenance_envelope). `LiveLedger` class loads + persists `data/live_portfolio/<account-redacted>/<date>/trades.jsonl`. NO live API calls; reads JSONL files.
- `lib/live_portfolio/ramp_gate.py` (~400 LOC) — pure: takes a `LiveLedger` + the ramp memo's gate spec (Sortino > 1.5 over 14 trading days at current rung) and returns `RampGateStatus { current_tier: int, target_tier: int, gate_status: Literal["soaking", "satisfied", "violated", "blocked"], days_in_tier: float, sortino_14d: float, blockers: list[str] }`. Strict; refuses to advance without explicit operator approval.
- `lib/live_portfolio/sortino.py` (~250 LOC) — pure: rolling Sortino over a list of returns; downside-deviation correctness; small-sample handling (return `None` with reason if n < 14).
- `lib/live_portfolio/seed.py` (~150 LOC) — pure: takes operator-confirmed fill JSON (the operator copies fill details from Robinhood app) and produces a `LiveTradeRecord`. Can be run interactively or non-interactively. Refuses to seed without provenance envelope.
- `services/live_portfolio_daemon/run.py` (~250 LOC) — async daemon: every hour, reload ledger, recompute ramp gate, publish to event bus on `ramp.gate.status.changed` if the status delta is non-trivial, write `data/live_portfolio/<account>/<date>/ramp_status.jsonl` with provenance.
- `services/live_portfolio_daemon/launchagent/com.sapphire.live-portfolio.plist.template` (do NOT install).
- `plugins/claw-sapphire/tools/internal/live_portfolio.py` (~350 LOC) — stdin-JSON. Actions: `seed-trade` (interactive: prompt operator for trade details), `ledger` (paste-safe summary, account hash redacted), `gate-status`, `sortino`, `forecast-rung-completion`. Mirrors `gemini_ooda` shape.
- `plugins/claw-sapphire/tools/live_portfolio.py` — 3-line shim.
- `tests/unit/test_live_portfolio_ledger.py` (≥ 22 cases): record persistence, ledger load/save, account-hash redaction, dedupe by trade_id + fill_at, malformed input rejection, provenance envelope shape.
- `tests/unit/test_live_portfolio_ramp_gate.py` (≥ 18 cases): each gate_status reachable, Sortino threshold boundary (1.49 vs 1.50 vs 1.51), days-in-tier counting (trading days only, no weekends), blockers list (kill_switch_active / confirmation_firewall_pending / sortino_below_threshold / days_in_tier_insufficient).
- `tests/unit/test_live_portfolio_sortino.py` (≥ 12 cases): correctness vs scipy reference, NaN handling, all-positive returns, all-zero returns, single-data-point.
- `services/live_portfolio_daemon/tests/test_run.py` (≥ 8 cases) OR `tests/unit/test_live_portfolio_daemon_run.py`.
- `plugins/claw-sapphire/tests/test_live_portfolio.py` (≥ 12 plugin tests).
- `infra/tool-registry.yaml` — append `live_portfolio` under "Trading & signals".
- **Seed file**: `data/live_portfolio/.gitkeep` plus a sample `data/live_portfolio/EXAMPLE-account-hash/2026-04-28/trades.jsonl` with a redacted-but-realistic fictitious trade so the dashboard has something to render in tests. **DO NOT** seed the operator's actual ...5966 trade in this PR — that's an operator action documented in the runbook.
- `docs/products/live-capital-ledger-0.1.0.md` (1500+ words) — buyer-facing. Walk through: how the $5 fill becomes a record, how the 14-day Sortino window ticks, what advances the gate, what blocks it, what an operator sees on the dashboard.
- `docs/ops/live-capital-ledger-runbook.md` (1500+ words) — operator runbook. **The seeding procedure is the longest section**: how operator pulls fill details from Robinhood app → runs `python3 -m plugins.claw-sapphire.tools.live_portfolio seed-trade` → confirms the resulting JSONL entry → optionally enables the daemon. Include the exact Robinhood fields to copy (Date filled / Symbol / Type / Limit price / Filled at / Amount filled / Filled notional value / Fee / Total cost).

**Constraints**:
- **No live API calls.** Reading is from operator-pasted JSON files only. No `requests.get(robinhood.com)`.
- **Account hash mandatory**: never persist the raw account number. Hash with `lib/security/pii_redactor.per_tenant_hash` (or equivalent if the helper isn't yet exposed) using a per-account salt. Documented in the runbook.
- **Source-email redaction**: if the operator pastes the Robinhood email, it MUST be redacted (full names of Ari / spouse / etc., transaction IDs beyond a 6-char prefix, full account numbers, full bank routing) before persistence.
- **Ramp gate is read-only**: this lane does NOT trigger trades. Gate status is published as a signal; the operator advances rungs manually after reviewing the status.
- **Kill-switch respect**: every gate-status check first verifies kill_switch is INACTIVE; if active, gate_status is forced to `blocked`.
- **Time-zone discipline**: all timestamps are UTC in storage; display can be local-tz in dashboards.

**PR title**: `feat(trading): live capital ledger + ramp gate engine 0.1.0`

---

### LANE 2 — Multi-Agent Audit Panel (closes the trust loop on autonomous merging)

**Why it matters**: Across Tranches 1-4 + sprints, Codex and Claude have admin-merged ~70+ PRs. None of those merges have been independently audited. A reviewer asks: "what's been getting merged, who pushed it, did any PR change a kill-switch invariant without coverage, did any commit message lie about scope?" There is currently no panel that answers this. This lane builds it. The panel runs weekly, reads the merged PR history, applies adversarial heuristics, and opens a `audit-panel`-labelled GitHub issue with findings.

This is the artifact that lets a buyer trust autonomous merging long-term. The honest framing: "Sapphire merges autonomously, but the audit panel reviews every merge weekly with red-team scoring."

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-audit-panel` on `feat/multi-agent-audit-panel`.

**Templates to read first**:
- `docs/security/adversarial-intelligence-threat-model-2026-04-28.md` — adversarial framing.
- `lib/security/adversarial_detectors.py` — detector pattern (Tranche 4 Lane 5).
- `plugins/claw-sapphire/tools/internal/dev_pulse.py` — cross-PR pulse pattern.
- `docs/handoffs/` — read 5+ recent handoff docs to understand merge cadence.

**Files**:
- `lib/audit_panel/__init__.py`
- `lib/audit_panel/heuristics.py` (~600 LOC) — pure detectors, each takes a `MergedPR` shape and returns `Finding | None`:
  - `oversize_diff` — PRs with > 2,000 lines changed across > 15 files.
  - `weak_commit_message` — commits where subject line < 10 chars or matches `^(wip|fix|update|misc)$`.
  - `kill_switch_touched_without_review` — PRs that modified `lib/core/kill_switch.py` / `confirmation_firewall.py` / `risk_kernel.py` without an `@arigatoexpress` review.
  - `tests_missing_for_new_module` — PRs that added a new `.py` file in `lib/` or `plugins/` without a corresponding `tests/unit/test_*.py`.
  - `scope_creep` — commits whose subject mentions one area but whose diff touched 5+ unrelated areas.
  - `secret_signature` — diff containing patterns matching API-key shapes (use existing `lib/security/pii_redactor` regexes).
  - `provenance_envelope_missing` — PRs that added a `data/<area>/*.json` artifact without a sibling `*.envelope.json`.
  - `failed_check_overridden` — PRs admin-merged while statusCheckRollup had FAILURE.
  - `ci_skip_dropped` — commits whose squash subject lacks `[skip ci]` in a no-spend session.
- `lib/audit_panel/scorer.py` (~250 LOC) — pure: aggregates findings into a per-PR `RiskScore` ∈ [0, 1] and an overall panel `RiskHistogram`.
- `lib/audit_panel/reporter.py` (~300 LOC) — pure: renders findings into a paste-safe Markdown report with sections (Critical / High / Medium / Low / Informational).
- `services/audit_panel/run.py` (~350 LOC) — script: pulls last week's merged PRs via `gh pr list --state merged --search "merged:>=<7-days-ago>"`, runs heuristics, scores, renders report, opens a `audit-panel`-labelled issue if any Critical or High findings; otherwise comments on the open `audit-panel`-rolling-summary issue (creates one if none exists).
- `services/audit_panel/launchagent/com.sapphire.audit-panel.plist.template` — weekly fire (configurable).
- `plugins/claw-sapphire/tools/internal/audit_panel.py` (~300 LOC) — stdin-JSON. Actions: `run-once`, `latest-report`, `pr-score <number>`, `histogram` (last 30 days).
- `plugins/claw-sapphire/tools/audit_panel.py` — shim.
- `tests/unit/test_audit_panel_heuristics.py` (≥ 28 cases): each heuristic above gets ≥ 3 cases (positive trip, negative no-trip, edge case).
- `tests/unit/test_audit_panel_scorer.py` (≥ 14 cases).
- `tests/unit/test_audit_panel_reporter.py` (≥ 12 cases): paste-safe rendering, no PR body verbatim copy (always summarized).
- `tests/unit/test_audit_panel_run.py` (≥ 10 cases): mock `gh` subprocess, weekly window logic, idempotent runs.
- `plugins/claw-sapphire/tests/test_audit_panel.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `audit_panel`.
- `docs/products/audit-panel-0.1.0.md` (1500+ words). Walk through what each heuristic catches with a real or synthetic example. Include the buyer pitch: "this is how Sapphire stays trustworthy under autonomous operation."
- `docs/ops/audit-panel-runbook.md` (1500+ words).

**Caps**:
- `MAX_PRS_PER_RUN = 200`
- `MAX_REPORT_BYTES = 50_000` (truncate report if exceeded; link to full JSON sidecar)
- `MAX_LIVE_GH_API_CALLS_PER_HOUR = 30`

**Constraints**:
- **Read-only**. The audit panel NEVER pushes commits, NEVER merges PRs, NEVER closes/reopens PRs/issues beyond the rolling-summary issue it owns.
- **Paste-safe output**. PR titles and SHAs are fine; full PR diff content NEVER goes in the report.
- **Idempotent**: running twice in the same week produces the same report (modulo new merges).

**PR title**: `feat(security): multi-agent audit panel 0.1.0`

---

### LANE 3 — Narrative Engine Self-Evaluation Loop

**Why it matters**: Tranche 4 Lane 1 shipped the LLM narrative synthesis engine. It generates theses but **has no feedback loop**. Without self-evaluation, a buyer's first question is "how do you know it's getting better?" — and the answer is currently "we don't measure". This lane builds the feedback loop: backtest the narrative engine against past correlated signals, compute prediction-quality time series, surface where it excels and where it fails.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-narrative-self-eval` on `feat/narrative-self-evaluation`.

**Templates to read first**:
- `lib/synthesis/narrative_engine.py` — the engine being evaluated.
- `lib/synthesis/rubric.py` — existing rubric.
- `lib/analytics/prediction_accuracy.py` — pattern for accuracy time series (existing in `lib/analytics/`).
- `plugins/claw-sapphire/tools/internal/vertex_eval.py` — eval-harness pattern.

**Files**:
- `lib/narrative_evaluation/__init__.py`
- `lib/narrative_evaluation/scorer.py` (~400 LOC) — pure: takes a `NarrativeThesis` (from Lane 1 of Tranche 4) and the actual outcome over its claimed horizon (from `data/correlated_signals/` / `data/signals/`), returns `OutcomeScore { directional_correctness: bool, magnitude_correctness: float, invalidator_triggered: bool, time_to_resolution_hours: float, surprise_score: float }`. The surprise score captures "did this thesis predict something the rules-based correlator missed?"
- `lib/narrative_evaluation/aggregator.py` (~350 LOC) — pure: computes rolling statistics: directional accuracy by symbol / by timeframe / by edge-score-bucket / by source-mix; identifies regime-conditional accuracy ("narratives are 65% directional in `risk_on_correlated` but only 42% in `regime_uncertain`").
- `lib/narrative_evaluation/diagnostics.py` (~300 LOC) — pure: surfaces "what the engine consistently gets wrong": specific false-positive patterns, persistent confidence-miscalibration, sources-mix anti-patterns.
- `services/narrative_evaluation/run.py` (~250 LOC) — daemon (configurable cadence; default daily): for each `NarrativeThesis` whose horizon has elapsed, score it, write `data/narrative_evaluation/<date>/scores.jsonl`, update rolling aggregates at `data/narrative_evaluation/aggregates/<period>.json`.
- `services/dashboard/templates/pages/narrative_eval.html` — new dashboard page. Sections: Headline accuracy stats / Per-symbol breakdown / Regime-conditional table / Top false-positive patterns / Calibration plot (confidence vs realized accuracy).
- `services/dashboard/app.py` — `/narrative-eval` route + `/api/narrative-eval-summary` + `/api/narrative-eval-aggregates`.
- `plugins/claw-sapphire/tools/internal/narrative_eval.py` (~350 LOC) — stdin-JSON. Actions: `score-thesis <id>`, `aggregates`, `diagnostics`, `calibration`.
- `plugins/claw-sapphire/tools/narrative_eval.py` — shim.
- `tests/unit/test_narrative_evaluation_scorer.py` (≥ 22 cases).
- `tests/unit/test_narrative_evaluation_aggregator.py` (≥ 18 cases).
- `tests/unit/test_narrative_evaluation_diagnostics.py` (≥ 14 cases).
- `tests/unit/test_dashboard_narrative_eval_routes.py` (≥ 10 cases).
- `plugins/claw-sapphire/tests/test_narrative_eval.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `narrative_eval`.
- `docs/products/narrative-self-evaluation-0.1.0.md` (1500+ words).
- `docs/ops/narrative-eval-runbook.md` (1200+ words).

**Constraints**:
- **No live LLM calls** in the evaluator. Re-uses the dry-run mock or actual past outputs.
- **Honest diagnostics**: do NOT cherry-pick metrics; report all dimensions even where the engine looks bad.
- **Idempotent scoring**: same thesis + same outcome → same score.

**PR title**: `feat(synthesis): narrative engine self-evaluation 0.1.0`

---

### LANE 4 — Research Notes Pipeline (LP-grade, multi-modal)

**Why it matters**: Sapphire's `data/backtests/strategies/` directory has ~756 backtests across 7 quant strategies. The output is JSON; humans don't read JSON. There is no "research note" — the polished memo a CTO at an LP forwards to a portfolio manager. This lane builds the pipeline: from backtest outputs → polished multi-modal research note (text + equity-curve chart + drawdown chart + per-symbol table + thesis paragraph + risks section). One PDF per strategy per period, provenance-stamped, ready to share.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-research-notes-pipeline` on `feat/research-notes-pipeline`.

**Templates to read first**:
- `lib/analytics/strategy_performance.py` — equity curve + drawdown computation.
- `lib/analytics/backtest_results.py` — JSON ingest.
- `lib/synthesis/narrative_engine.py` — narrative generation (this lane reuses it for the thesis paragraph).
- `lib/content/draft_generator.py` (in `lib/content/`) — existing report-generator scaffolding.

**Files**:
- `lib/research_notes/__init__.py`
- `lib/research_notes/composer.py` (~500 LOC) — pure: takes a strategy result + sweep aggregates + market context (cross-asset regime from Lane 2 of Tranche 4, on-chain regime from Lane 6 of Tranche 4) and returns a `ResearchNote` dataclass with all sections.
- `lib/research_notes/visualizations.py` (~400 LOC) — pure (matplotlib): renders equity curve PNG, drawdown PNG, monthly returns heatmap, per-symbol bar chart. ALL deterministic (fixed-seed where applicable, no time-of-render text).
- `lib/research_notes/renderer.py` (~350 LOC) — composes ResearchNote + PNG charts into a multi-page PDF. Uses the `anthropic-skills:pdf` skill if available; otherwise a `reportlab`-based fallback (add `reportlab>=4.0` as a dev-only dep — this is the SOLE new dep authorized in Tranche 5).
- `services/research_notes/build.py` — script: enumerate completed backtest sweeps, compose research notes, render, persist to `data/research_notes/<date>/<strategy>/research-note.pdf` + sibling `.envelope.json`.
- `plugins/claw-sapphire/tools/internal/research_notes.py` (~300 LOC) — stdin-JSON. Actions: `compose <strategy>`, `render <strategy>`, `latest`, `aggregate-summary` (top 3 strategies of the period).
- `plugins/claw-sapphire/tools/research_notes.py` — shim.
- `tests/unit/test_research_notes_composer.py` (≥ 20 cases).
- `tests/unit/test_research_notes_visualizations.py` (≥ 14 cases): determinism, no-leak (charts don't include real customer data).
- `tests/unit/test_research_notes_renderer.py` (≥ 10 cases): PDF byte determinism, envelope shape.
- `plugins/claw-sapphire/tests/test_research_notes.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `research_notes`.
- `docs/products/research-notes-pipeline-0.1.0.md` (1500+ words).
- `docs/ops/research-notes-runbook.md` (1200+ words).
- **Sample output**: `data/research_notes/2026-04-29/sapphire-composite/research-note.pdf` — a real generated note from the existing sweep.

**Constraints**:
- **Reproducible**: same input + same SHA → byte-identical PDF.
- **Buyer-readable**: no jargon assumed; one-line definitions for Sortino, deflated Sharpe, etc., on first use.
- **No live data calls** in tests; all from fixture sweeps.

**PR title**: `feat(research): LP-grade research notes pipeline 0.1.0`

---

### LANE 5 — Intelligence Breadth Pass (5 new signal sources)

**Why it matters**: Tranche 4 wired BIG sources (cross-asset, macro, on-chain, hyperliquid counter-party). The intelligence aperture is wide but not WIDE-WIDE. Five more sources broaden it materially. Each is a new adapter that plugs into the signal correlator.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-intel-breadth-pass` on `feat/intelligence-breadth-pass`.

**Templates to read first**:
- `lib/correlator/sources.py` — adapter pattern from Tranche 4.
- `lib/macro/sources.py` — feedparser-based source pattern.

**The 5 new sources**:

1. **DeFiLlama** (`lib/sources/defillama.py`) — TVL by chain / by protocol / protocol revenues / forks. API: `https://api.llama.fi/`. Free tier; cite docs URL. Adapter emits `tvl.shift`, `protocol.revenue.spike` signals.
2. **Dune Analytics named queries** (`lib/sources/dune.py`) — operator-curated query IDs (start with 5: BTC ETF flows, ETH staking yield, stablecoin supply, top wallet flows, gas-heatmap). Free with API key. Adapter caches results 1h.
3. **Twitter / X public sentiment** (`lib/sources/x_sentiment.py`) — official Twitter API v2 (Free Tier: 1,500 tweets/month — be explicit about budget). Track 50 curated handles (operator-supplied list, defaults to empty + `~/.sapphire/x_sentiment_handles.yaml` config). Sentiment via existing `lib/intel/` sentiment helpers.
4. **News API** (`lib/sources/news.py`) — `https://newsapi.org/` free-tier with API key. Categorize headlines (financial / regulatory / tech / macro). Adapter emits `news.event.<category>` signals.
5. **Job postings labor signal** (`lib/sources/labor.py`) — public job-board RSS feeds (USAJobs.gov has structured data; corporate career-page sitemaps). NO scraping LinkedIn/Indeed (TOS). Track sectors: tech, finance, crypto, defense. Adapter emits `labor.posting.spike` and `labor.posting.contraction` signals over rolling windows.

**Files (per source, common shape)**:
- `lib/sources/<name>.py` — pure adapter. Live behind `SAPPHIRE_<NAME>_LIVE=1` + key in `~/.sapphire/secrets.env`. Caps. Cache.
- `tests/unit/test_sources_<name>.py` (≥ 12 cases each).

**Plus**:
- `lib/sources/__init__.py` — registry export.
- `lib/correlator/sources.py` — extend with adapters that wrap each new source as a correlator-input source. (This is the ONLY exception to the "do not modify Tranche 4 surfaces" rule — single-line additions per source to register them, plus tests that already exist.)
- `infra/tool-registry.yaml` — five new entries (one per source).
- `docs/products/intelligence-breadth-pass-0.1.0.md` (1500+ words; cite primary docs URL for each source).
- `docs/ops/intelligence-breadth-runbook.md` (1500+ words).

**Constraints**:
- **All free-tier APIs**: refuse to add a source that has no free or trial tier the operator could enable.
- **No scraping TOS-violating sites**: explicitly NOT LinkedIn, NOT Indeed (use their official APIs only — usually paid; defer).
- **Cite primary docs** in code comments + product doc.
- **Live mode is operator-flagged per source**.

**PR title**: `feat(intel): intelligence breadth pass — 5 new signal sources 0.1.0`

---

### LANE 6 — Sapphire Reproducibility Playbook (`make sapphire-on-fresh-mac`)

**Why it matters**: Right now, a buyer's CTO can read about Sapphire but cannot SPIN IT UP. Their diligence team has no path from "interesting on paper" to "running on my MacBook in 30 minutes". This lane builds it: a single `make sapphire-on-fresh-mac` that bootstraps everything in demo mode (no operator credentials needed). Demo mode runs against fixture data and mock external APIs; the operator can flip live mode after the demo session if they want.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-reproducibility` on `feat/reproducibility-playbook`.

**Files**:
- `scripts/ops/bootstrap_fresh_mac.sh` (~300 LOC) — POSIX bash. Idempotent. Steps:
  1. Verify macOS (Linux fallback via brew).
  2. Install `homebrew` if missing.
  3. Install pinned versions of: python@3.12, redis, sqlite, jq, gh, pyenv, uv, ruff, just, ollama (all via brew).
  4. Clone Sapphire if not present; otherwise skip clone.
  5. Set up Python venv with pinned `requirements-test.txt`.
  6. Bootstrap minimal `~/.sapphire/secrets.env` from `infra/secrets.env.example` (all values are `DEMO_*` placeholders; refuses live mode).
  7. Install LaunchAgents from `infra/launchagents/` but with `RunAtLoad=false` (operator opts in).
  8. Run a smoke verify: `local_ci_verify.py --quiet` should pass.
  9. Print a "next steps" summary for the operator.
- `scripts/ops/teardown_fresh_mac.sh` (~150 LOC) — reverse the bootstrap (LaunchAgents removed, Python venv unlinked, optional brew uninstalls).
- `infra/secrets.env.example` — every secret name documented with `DEMO_*` placeholder + a `# Source:` comment pointing at where to get the real value.
- `infra/bootstrap/<config>` — minimal default configs that demo mode uses (e.g., `~/.sapphire/correlator_weights.yaml.example`, `~/.sapphire/telegram_channels.yaml.example`, `~/.sapphire/hyperliquid_symbols.yaml.example`).
- `Makefile` — add target `sapphire-on-fresh-mac` that runs the bootstrap + verifies. Plus `sapphire-demo-up` (start dashboard + correlator daemon in demo mode), `sapphire-demo-down` (stop), `sapphire-demo-reset` (full teardown + re-bootstrap).
- `docs/setup/reproducibility-playbook.md` (3000+ words) — the canonical fresh-mac walkthrough. Sections:
  1. **For diligence reviewers** — quickest path. 30-minute promise.
  2. **What demo mode shows** — concretely, what URLs come up, what data they render.
  3. **Going live** — operator opt-in checklist for each external API.
  4. **Troubleshooting** — common failures (brew permissions, port conflicts, redis already running, ollama models not pulled).
  5. **Architecture refresher** — pointers to `docs/architecture-overview.md` and the diligence packet.
  6. **Demo-mode safety statement** — explicitly says "demo mode cannot connect to real exchange / payment / messaging APIs even if env flags are flipped".
- `tests/unit/test_bootstrap_fresh_mac_dryrun.py` (≥ 12 cases) — dry-run mode (`SAPPHIRE_BOOTSTRAP_DRY_RUN=1`) traces every shell command without executing; tests assert the expected command sequence.
- `tests/unit/test_makefile_targets_present.py` (≥ 6 cases) — every documented target exists in Makefile and resolves.

**Constraints**:
- **Demo mode is the default**. Live mode requires operator-pasted secrets AND env flag flips AFTER bootstrap completes.
- **Idempotent**: running bootstrap twice doesn't break anything.
- **No operator-personal data**: the bootstrap NEVER pulls operator's `~/.sapphire/secrets.env` into the demo install.
- **macOS first**: Linux is best-effort fallback. Document Windows as "use WSL2" with pointer to a future Windows-native pass.

**PR title**: `feat(setup): reproducibility playbook — fresh-mac bootstrap`

---

### LANE 7 — Customer-Facing Product Surface (`web/customer/` + API + pricing)

**Why it matters**: Sapphire is currently 100% internal tooling. The acquirer microsite (Tranche 3 Lane 4) is buyer-facing for ACQUISITION. The actual customer-facing PRODUCT surface — pricing, sample API access, threat-intel feed, narrative sample — does not exist. This lane builds it. Pivots Sapphire from "interesting tech project" toward "potential B2B revenue stream" — which dramatically increases acquisition optionality (a potential acquirer can see "buy us, AND get a customer business").

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-customer-surface` on `feat/customer-product-surface`.

**Files**:
- `web/customer/index.html` — single-page static HTML/CSS site (NO JS framework). Sections:
  1. **What we sell** — three product lines: Threat-Intel Feed, Multi-Source Narrative Stream, Cross-Asset Correlation API.
  2. **Pricing** — explicit tiers: Starter (free, 100 req/day), Pro ($49/mo, 10k req/day), Enterprise (contact, unlimited + SLA). 
  3. **Sample API output** — three live JSON samples, one per product line, drawn from real (paste-safe) Sapphire data.
  4. **Trust + safety** — links to `docs/security/` and the audit panel.
  5. **Get started** — operator's contact email + a stub OAuth signup flow that's NOT WIRED UP (clearly labelled "private beta — request access").
  6. **For acquirers** — link back to the acquirer microsite at `/acquirer/`.
- `web/customer/assets/styles.css` — vanilla CSS, mirror brand from `web/acquirer/assets/branding/`.
- `services/customer_api/__init__.py`
- `services/customer_api/app.py` (~400 LOC) — Flask app, `:9000`. Routes: `/v1/threat-intel`, `/v1/narrative`, `/v1/cross-asset`, `/v1/health`. Each returns sample paste-safe data with a `mock=true` field. Refuses to serve real data unless `SAPPHIRE_CUSTOMER_API_LIVE=1` AND payment infra verified.
- `services/customer_api/auth.py` (~200 LOC) — API key validation (NEVER calls real auth; demo mode accepts `DEMO_KEY_*`).
- `services/customer_api/rate_limiter.py` (~150 LOC) — per-key per-day request counter. In-memory; reset on restart. Demo mode logs but does not enforce.
- `services/customer_api/payments.py` (~200 LOC) — x402 micropayment gate stub. Reuses `lib/payments/x402_middleware.py`. Demo mode: returns 200 to all requests with `x-sapphire-billed: 0` header.
- `services/customer_api/launchagent/com.sapphire.customer-api.plist.template` — port 9000, demo mode by default.
- `tests/unit/test_customer_api_routes.py` (≥ 18 cases): all 3 endpoints + health, demo mode, mock-only response schema, refuses live without env flag, 404 on unknown route.
- `tests/unit/test_customer_api_auth.py` (≥ 10 cases).
- `tests/unit/test_customer_api_rate_limiter.py` (≥ 8 cases).
- `tests/unit/test_customer_api_payments.py` (≥ 8 cases): demo mode passes, live without payment infra refuses.
- `tests/unit/test_customer_microsite_html.py` (≥ 10 cases): every link target exists, no inline JS, no external resources.
- `docs/products/customer-product-surface-0.1.0.md` (2000+ words) — sales-and-product positioning (3 product lines, pricing rationale, customer ICP).
- `docs/ops/customer-api-runbook.md` (2000+ words) — operator runbook including: how to flip live mode (multiple gates), how to set up payment infrastructure (deferred; documented but not built), how to handle a real customer signup (defer to a future sales process — this lane explicitly stops at "private beta gate").

**Constraints**:
- **Demo mode is the ONLY mode this lane ships in**. Live mode requires payment infra + customer onboarding flows neither of which this lane builds.
- **No real customer data**. All sample API outputs are paste-safe synthetic.
- **Pricing is illustrative** — operator decides actual numbers before any commercial activity.
- **The OAuth signup flow is a stub**: the form posts to `/v1/private-beta-request` which logs the inquiry to `data/customer_api/private_beta_requests.jsonl` and emails operator (operator-flagged).
- **Acquirer connection**: customer site links to acquirer site clearly; an acquirer browsing the customer site sees the product side AND the acquisition pitch.

**PR title**: `feat(customer): customer-facing product surface 0.1.0`

---

### LANE 8 — Pine Strategy Generation Pipeline

**Why it matters**: Sapphire backtests 7 quant strategies with hundreds of parameter combinations. The winners are JSON. **TradingView users can't run JSON — they run Pine Script v5.** Sapphire already has a TradingView MCP bridge (`tradingview-mcp-v2`). This lane closes the loop: take the top backtest configs, auto-generate Pine Script v5 strategies, push them to TradingView via the MCP. The strategy IP becomes deployable infrastructure on the world's most-used charting platform.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-pine-generation` on `feat/pine-strategy-generation`.

**Templates to read first**:
- `lib/analytics/strategies.py` — the 7 strategies' Python implementations.
- `pine/standalone/` — existing hand-written Pine v5 strategies; structure to mimic.
- `tradingview-mcp-v2` (in operator's other repo, READ-ONLY) — MCP bridge surface.

**Files**:
- `lib/pine_generation/__init__.py`
- `lib/pine_generation/translator.py` (~600 LOC) — pure: takes a Python strategy + a parameter set + a symbol and emits Pine Script v5 source. Supports the 7 existing strategies (RegimeAwareRSI, FundingRateContrarian, CorrelationBreakout, MultiTFMomentum, SapphireComposite, plus base + params).
- `lib/pine_generation/templates/` — Pine v5 templates per strategy class (`.pine.j2` Jinja templates).
- `lib/pine_generation/validator.py` (~250 LOC) — pure: lints generated Pine via heuristics (balanced parens, no `var <type> ?` ambiguity, `strategy()` declaration well-formed); refuses to emit if validation fails.
- `services/pine_generation/build.py` (~300 LOC) — pulls top-N backtest results from `data/backtests/strategies/best_per_symbol_*.json`, generates Pine for each, persists to `pine/generated/<date>/<strategy>-<symbol>.pine`.
- `plugins/claw-sapphire/tools/internal/pine_generation.py` (~300 LOC) — stdin-JSON. Actions: `generate <strategy> <symbol>`, `latest`, `validate <pine-source>`, `push-to-tv` (calls existing tradingview-mcp; refuses unless `SAPPHIRE_PINE_TV_PUSH_LIVE=1`).
- `plugins/claw-sapphire/tools/pine_generation.py` — shim.
- `tests/unit/test_pine_generation_translator.py` (≥ 24 cases): ≥ 3 cases per strategy class, generated Pine parses through the validator, parameter-substitution correctness.
- `tests/unit/test_pine_generation_validator.py` (≥ 14 cases): catches malformed Pine, accepts well-formed.
- `plugins/claw-sapphire/tests/test_pine_generation.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `pine_generation`.
- `docs/products/pine-generation-0.1.0.md` (1500+ words). Walk through one strategy's Python → Pine translation.
- `docs/ops/pine-generation-runbook.md` (1200+ words).
- **Sample output**: `pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine` — a real generated strategy from the latest sweep.

**Constraints**:
- **The TradingView push is operator-gated**. This lane SHIPS the generation pipeline; pushing to TV requires the operator to flip `SAPPHIRE_PINE_TV_PUSH_LIVE=1` and run the action explicitly.
- **No new dep on `tradingview-mcp-v2` repo** — Sapphire calls the local MCP bridge that's already running.
- **Generated Pine is NOT for live trading** without operator review. The runbook is explicit: every generated strategy must be paper-tested in TV before going live.

**PR title**: `feat(strategies): pine v5 strategy generation pipeline 0.1.0`

---

### LANE 9 — Tranche 5 Integration Pass (the compound)

**Why it matters**: 8 lanes shipped 8 surfaces. The compound edge requires they connect. This lane wires:

1. **Live Capital Ledger (1) ↔ Audit Panel (2)**: audit panel consumes ledger updates; flags any trade that's outside expected slippage from its limit price.
2. **Live Capital Ledger (1) ↔ Customer API (7)**: customer API publishes a paste-safe "ramp-tier" status (e.g., "Sapphire is currently at $5 paper-soak rung") so customers know the safety posture they're consuming.
3. **Narrative Self-Eval (3) ↔ Audit Panel (2)**: audit panel surfaces narrative-engine accuracy metrics in its weekly report.
4. **Narrative Self-Eval (3) ↔ Research Notes (4)**: research notes for active strategies include the engine's recent accuracy on related theses.
5. **Intelligence Breadth (5) ↔ Correlator + Narrative**: the 5 new sources flow into the existing correlator + narrative engine. (Most of the wiring is in Lane 5; Lane 9 verifies end-to-end + integration test.)
6. **Reproducibility Playbook (6) ↔ Customer Surface (7)**: `make sapphire-on-fresh-mac` brings up demo mode INCLUDING the customer API on `:9000` so a buyer can hit it.
7. **Pine Generation (8) ↔ Research Notes (4)**: research notes embed the generated Pine source as an appendix per strategy.
8. **Tranche 5 surfaces ↔ Observability dashboard (Tranche 3)**: extend the `/observability` panel with cards for each new daemon (live_portfolio, audit_panel, narrative_evaluation, customer_api, plus the 5 new intel sources).
9. **Tranche 5 surfaces ↔ Acquirer microsite (Tranche 3)**: add 4 new capability cards to `web/acquirer/index.html` for the Tranche 5 lanes.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-t5-integration` on `feat/tranche-5-integration-pass`.

**Files**: this PR is mostly imports + small additive wiring + integration tests that exercise the cross-lane flows. Each integration is exercised by ONE end-to-end test that runs against fully-mocked Lane outputs.

- `lib/intelligence/tranche5_integration.py` — single module that holds the wiring. Pure imports + small adapter functions.
- `tests/unit/test_tranche5_integration.py` (≥ 18 cases) — one per wiring above.
- `services/dashboard/templates/pages/observability.html` — extend with 8 cards (additive only).
- `web/acquirer/index.html` — add 4 capability cards.
- `docs/products/tranche-5-integration-pass.md` (1000+ words) — explains how the surfaces compound.

**Constraints**:
- **Additive only**. No refactors of prior-lane code.
- **End-to-end tests** must exist for every wiring above.
- The integration PR is the ONE that updates README test count + plugin tool count + scheduled-task count, since it's the last to merge in Tranche 5.

**PR title**: `feat(intelligence): tranche-5 integration pass — the compound edge`

---

## 4. Verification protocol (every lane)

Before opening a PR, all six green from inside the worktree:

```bash
ruff check .
/usr/local/bin/python3 -m pytest <NEW_TEST_FILES> -q --tb=short
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

`0 FAIL` mandatory. Run unit + plugin pytest blocks SEPARATELY.

For lanes that touch the live capital path (Lane 1) and customer-payment path (Lane 7), additionally run:
```bash
/usr/local/bin/python3 -m pytest tests/unit/test_kill_switch* tests/unit/test_confirmation_firewall* -q
/usr/local/bin/python3 -m pytest tests/unit/test_x402* -q
```
These existing test suites must continue to pass — Lanes 1 and 7 are not allowed to break the safety gates they read.

---

## 5. PR template

Each PR body MUST include:
- **What this enables** — acquisition framing.
- **Cross-lane integration** — how this lane plugs into Tranche 5's other lanes (and Tranche 1-4 surfaces).
- **Safety posture** — env gates, caps, no-secrets-at-rest, kill-switch respect.
- **Local verification** — six command outputs.
- **Files changed** — file list.
- **Follow-ups not in this PR** — be honest.

---

## 6. Merge protocol

Use `~/Code/Sapphire/scripts/ops/sapphire_safe_merge.sh <PR>`. Fallback:
```bash
TITLE=$(gh pr view <N> --json title --jq '.title')
SUBJECT="${TITLE} [skip ci]"
gh -R arigatoexpress/Sapphire pr merge <N> --squash --admin --delete-branch -t "$SUBJECT"
gh run list --limit 5 --json databaseId,status --jq '.[] | select(.status=="queued" or .status=="in_progress") | .databaseId'
```

If a registry-yaml conflict between two lanes: rebase the second on the merged first, regenerate the registry append, re-verify, push.

---

## 7. Closeout deliverable

After all 9 PRs merge, write `docs/handoffs/codex-megaprompt-tranche-5-2026-04-30-report.md` with:

1. **Final main SHA** + open PR/issue counts.
2. **Per-lane status table** — including key cross-lane integrations exercised.
3. **Verification at handoff** — six commands' tail output.
4. **Operator-owed actions** — Glassnode key (carry-forward), Santiment, ETH/SOL RPC, Gemini live narrative, plus NEW: Robinhood fill seeding into the live ledger, customer-API beta-tester recruitment, TradingView strategy publishing approval.
5. **Skipped lanes (if any)** with one paragraph each.
6. **Tranche 6 backlog** — what's next? (Suggestions: live customer onboarding, real Glassnode/Santiment soak, paper-shadow-controller wiring deeper, Pine strategy live-monitoring, reproducibility playbook on Linux + Windows.)
7. **Squash-merge subject audit** — every Tranche 5 squash subject ended with `[skip ci]`.
8. **Compound-edge evidence** — concretely show that Tranche 5 produces what Tranches 1-4 couldn't:
   - Demo a `make sapphire-on-fresh-mac` run on a clean macOS VM (or document the operator-led test).
   - Show the live capital ledger rendering the seeded $5 fill.
   - Show one weekly audit-panel report.
   - Show one narrative-eval aggregate.
   - Show one research note PDF.
   - Show one generated Pine v5 strategy.
   - Show the customer microsite serving sample API.

Then update `~/.claude/projects/-Users-aribs/memory/MEMORY.md` with one line pointing to a new `project_2026-04-30_codex_tranche_5.md`.

---

## 8. Posture reminders

- **Quality over quantity.** Polished single deliverables.
- **Honest framing**. Where Sapphire still falls short of the acquisition pitch, say so plainly.
- **Bounded LLM use** in build lanes. Mirror the established safety patterns precisely.
- **Provenance envelopes everywhere**.
- **Trading critical path is sacred**. Lane 1 ADDS new modules; it does NOT modify the gated files.
- **Customer surface is mock-default**. Lane 7 explicitly does not serve real customer payments.
- **Cross-lane awareness**. Even if your sub-agent is on a single lane, read the other lanes' specs so wiring boundaries are clear.
- **The integration-pass PR is non-optional**. The compound edge only exists if the wirings happen.
- **Reproducibility is the buyer's first test**. Lane 6 must work on a fresh macOS without operator credentials.

This is the tranche where Sapphire proves it can be **acquired and continued**: a buyer can spin it up, audit its autonomous merging history, see live capital evidence, read research notes, hit the customer API, and run generated strategies on TradingView. **All five capabilities cleared by the closeout.**

Now go.
