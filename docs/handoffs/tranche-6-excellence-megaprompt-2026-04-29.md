# Tranche 6 Excellence Megaprompt — 2026-04-29

> **Operator usage**: this megaprompt is **agent-agnostic**. It can be dispatched into a fresh Codex session, into Claude Code agents, or both in parallel. The orchestrator (Claude Code, this session) is dispatching Claude agents as the primary executor; Codex is welcome to pick up any leftover lane after their usage cap resets. Each lane is self-contained.

---

## 0. Mission

**Tranche 5** added compound surfaces — narrative synthesis, audit panel, customer-facing surface, reproducibility playbook, research notes, intelligence breadth, live capital ledger, Pine generation. The surface area is wide.

**Tranche 6** does NOT add new surfaces. **Tranche 6 makes the existing system measurably world-class** by closing the gap between "polished features that exist" and "rigorously verified, performance-characterized, operationally-mature system that an institutional acquirer would buy without hesitation".

The mental model: **Excellence as Compound Edge**. A buyer's diligence team asks five questions during deep due diligence:

1. **"How do you know it works?"** — answered by property-based + mutation tests (Lane 1).
2. **"What happens when it breaks?"** — answered by SLO definitions, runbook completeness, ADRs (Lane 2).
3. **"Can we reconstruct what it knew at time T?"** — answered by time-travel + replay (Lane 3).
4. **"How do you measure your edge over time?"** — answered by source-quality + signal SNR + walk-forward backtests (Lanes 4 + 5).
5. **"What does it cost to run, and is it efficient?"** — answered by inference mesh telemetry + token economics (Lane 6).

Plus two intelligence-depth lanes that broaden the aperture (Lane 7 SEC + earnings, Lane 8 chaos engineering on the event bus), and a final integration pass.

This is **deep work**. Lanes are bigger than Tranche 5's. **Quality over quantity.** A single well-done lane is worth more than three sloppy ones.

If your runtime supports parallel sub-agents, dispatch all 9 lanes concurrently. If not, do them sequentially in the order listed (highest-impact first).

---

## 1. Non-negotiable constraints

1. **No-spend posture.** `[skip ci]` on every commit. Use `~/Code/Sapphire/scripts/ops/sapphire_safe_merge.sh <PR>` for merges. Cancel queued runs after every merge.
2. **Don't touch the trading critical path** without operator confirmation: `services/alpha/`, `lib/portfolio/robinhood.py`, `lib/trading/`, `lib/analytics/risk_engine.py`, `lib/analytics/strategies.py`, `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`, `services/webhook/`, `contracts/`. Lane 5 (walk-forward backtests) READS `lib/analytics/strategies.py` but does NOT modify it; it adds new modules in `lib/analytics/walkforward/` instead.
3. **Stay out of prior tranches' surfaces** for refactoring. ADD new modules. Lane 9 (integration) is the only lane that may make additive imports.
4. **The fixture-clock vs impl-clock date-flake template** still applies — five known cases now (#377, #394, plus production-readiness sprint). Anytime a test uses `datetime.now()` against an impl that takes a `now` arg, monkey-patch with `FrozenDatetime`.
5. **Web research lanes (Lane 7)** must cite primary URLs with retrieval dates. NEVER fabricate quotes / statistics.
6. **Do not touch satellite repos.**
7. **Secrets are read-only and live-mode-only.**
8. **Provenance envelopes on all generated artifacts.**
9. **No README test counts during multi-lane work.** Lane 9 updates README once.
10. **Two new prod deps authorized in this tranche only**: `hypothesis>=6.130,<7` for property-based testing (Lane 1) and `mutmut>=2.5,<3` for mutation testing (Lane 1, dev-only). Everything else stdlib + already-pinned.
11. **Worktree-per-lane.** `~/Code/_worktrees/sapphire-<branch>`. Clean up when PR merges.
12. **Open PR but DO NOT auto-merge** unless local verification is green. The orchestrator (or operator) handles merging.
13. **Operator's stashed Hyperliquid live-executor work** at `git stash@{0}` and `stash@{1}` is OFF-LIMITS. It touches `lib/trading/` and is operator-review-pending.

---

## 2. Pre-flight + state at start

```bash
cd ~/Code/Sapphire
git fetch --all --quiet
git rev-parse --short HEAD                              # expect 65853f92 or descendant
gh pr list --state open --json number                   # expect ≤ 2 (Lane 8 Pine + #425 comms)
/usr/local/bin/python3 -m pytest tests/unit/ -q         # expect ≥ 5,166 passed
/usr/local/bin/python3 scripts/validate_tool_registry.py    # expect registry ≥ 58, errors=0
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -3   # expect 0 FAIL
git stash list | head -3                                # expect 2 hyperliquid live-executor stashes
```

If anything is off, write a pre-flight gap report and stop.

**Reference reading** (skim BEFORE any lane):
- `docs/handoffs/codex-megaprompt-tranche-5-compound-edge-2026-04-29.md` — what just landed.
- `docs/process/claude-force-multiplier-playbook-2026-04-29.md` — Codex vs Claude shape.
- `docs/competitive/landscape-2026-04-28.md` — what world-class looks like.
- `docs/architecture-overview.md`.
- `CLAUDE.md` — live state. Should now show 5,166+ tests, 58+ registry entries.

---

## 3. Lanes

**Nine lanes (8 build + 1 integration pass).** Order matters: highest-impact first.

---

### LANE 1 — Property-Based + Mutation Testing Pass (test rigor)

**Why it matters**: 5,166+ unit tests is a lot of tests. **Coverage ≠ correctness.** A buyer's CTO will ask: "are these tests rigorous, or are they example-based?" Without property tests + mutation testing, the answer is "example-based, mostly". This lane answers it differently: "property-based + mutation-tested, with documented mutation kill rate."

**Worktree + branch**: `~/Code/_worktrees/sapphire-test-rigor-pass` on `chore/property-and-mutation-testing-pass`.

**Files**:

- Add to `requirements-test.txt`: `hypothesis>=6.130,<7`, `mutmut>=2.5,<3`. **NEW deps authorized for this lane only.**
- `tests/property/__init__.py`
- `tests/property/test_pii_redactor_properties.py` (≥ 12 properties, including: redact(redact(x)) == redact(x); never increases sensitivity; respects PII type; locale stability over 100 fuzzed inputs; idempotent across CJK + diacritics + unicode-normalization edge cases).
- `tests/property/test_correlator_scoring_properties.py` (≥ 10 properties): edge_score bounded in [-1, +1] for all input shapes; agreement bonus monotone non-decreasing in num_corroborating_sources; freshness decay bounded below; deterministic given same input.
- `tests/property/test_live_portfolio_sortino_properties.py` (≥ 8 properties): Sortino agrees with manual calc to 1e-6 over 50 random returns series; small-sample returns None correctly; all-zero returns handled.
- `tests/property/test_observability_aggregator_properties.py` (≥ 6 properties): SystemSnapshot serializes deterministically; never emits PII; bounded size.
- `tests/property/test_audit_panel_heuristics_properties.py` (≥ 8 properties): each heuristic is monotone in the dimension it scores; never false-trips on synthetically-clean PRs; reporter output is paste-safe (no raw PR diffs).
- `scripts/ops/run_mutation_testing.py` — wrapper around `mutmut` that runs against `lib/security/pii_redactor.py`, `lib/correlator/scoring.py`, `lib/live_portfolio/sortino.py`, `lib/live_portfolio/ramp_gate.py`, and `lib/audit_panel/heuristics.py`. Outputs a per-module mutation kill rate to `data/test_rigor/mutation_report_<date>.json` + a paste-safe Markdown summary at `data/test_rigor/mutation_report_<date>.md`. **Operator-supervised: requires `SAPPHIRE_MUTATION_TEST_LIVE=1` because mutation testing takes hours.**
- `tests/unit/test_run_mutation_testing_dryrun.py` (≥ 6 cases): dry-run emits the expected command sequence.
- `docs/products/test-rigor-0.1.0.md` (1500+ words): explain property-based vs example-based, walk through 3 worked examples of properties catching bugs that examples missed.
- `docs/ops/test-rigor-runbook.md` (1000+ words).

**Caps**:
- Hypothesis examples per property: 100 default, 500 in CI mode (configurable via `HYPOTHESIS_PROFILE`).
- Mutation testing scoped to listed modules only (no whole-repo runs in this PR).

**Verification**:
- `pytest tests/property/ -q --tb=short` → all green
- `pytest tests/unit/ -q` → 0 failures (existing tests unaffected)
- Mutation testing dry-run smoke (live run is operator-gated)

**PR title**: `chore(tests): property-based + mutation testing pass 0.1.0`

---

### LANE 2 — ADRs + Runbook Completeness + SLO Definitions

**Why it matters**: Sapphire has 19 services, 23 LaunchAgents, hundreds of design decisions made across 8 tranches. Many are undocumented. A buyer's principal engineer cannot understand the system without ADRs + runbooks. Today, ADRs are zero; runbook coverage is partial.

**Worktree + branch**: `~/Code/_worktrees/sapphire-adrs-runbooks` on `docs/adrs-runbooks-slos-tranche-6`.

**Files**:

- `docs/adr/0000-template.md` — ADR template (Title, Status, Context, Decision, Consequences, Alternatives Considered).
- `docs/adr/0001-no-spend-posture.md` — why `[skip ci]` + `vars.SAPPHIRE_RUNNER` + safe-merge wrapper.
- `docs/adr/0002-worktree-per-lane.md` — why parallel agents get isolated worktrees.
- `docs/adr/0003-trading-critical-path-codeowners-gate.md`.
- `docs/adr/0004-bounded-llm-tools-via-env-flag-pattern.md` — gemini_ooda → vertex_eval → narrative_synthesis pattern.
- `docs/adr/0005-provenance-envelopes-everywhere.md`.
- `docs/adr/0006-fixture-clock-vs-impl-clock-test-template.md`.
- `docs/adr/0007-correlator-deterministic-rules-then-llm-narrative.md`.
- `docs/adr/0008-customer-surface-mock-default-with-three-gates.md`.
- `docs/adr/0009-foundry-ontology-as-acquisition-bridge.md`.
- `docs/adr/0010-cowork-vs-claude-code-vs-codex-split.md` (cite the playbook).
- `docs/adr/index.md` — index of all ADRs with one-line summaries.
- `docs/ops/runbook-coverage-audit-2026-04-29.md` — for each of the 19 services + 23 LaunchAgents + 8 cloud routines: does a runbook exist? Quality score (1-5)? Gap actions?
- `docs/ops/slos.md` — SLO definitions per service: availability target, latency p99 target, error rate target, freshness target. Where SLO exceeds current measurement, mark "aspirational" explicitly.
- `tests/unit/test_adr_index_resolves.py` (≥ 8 cases): every ADR file linked from the index exists; every status is one of {proposed, accepted, deprecated, superseded}; every superseded ADR points at its successor.
- `tests/unit/test_runbook_coverage_completeness.py` (≥ 6 cases): every entry in the audit doc points to a real path; quality scores are in 1-5; gap actions are non-empty when score < 4.

**Constraints**: docs-only. Honest grading — if a runbook is bad, score it bad.

**PR title**: `docs(ops): ADRs + runbook coverage audit + SLO definitions`

---

### LANE 3 — Time-Travel + Replay Capability

**Why it matters**: A buyer asks "what did Sapphire think 3 days ago about BTC?" Today, the answer is "go grep the logs." With time-travel + replay, the answer is "run `sapphire timetravel --asset BTC --at 2026-04-26T18:00:00Z`." This is a unique capability that institutional intelligence systems rarely have.

**Worktree + branch**: `~/Code/_worktrees/sapphire-time-travel` on `feat/time-travel-and-replay`.

**Files**:
- `lib/timetravel/__init__.py`
- `lib/timetravel/snapshot.py` (~400 LOC) — pure: `take_snapshot(at: datetime, scope: list[str]) -> SystemSnapshot`. Pulls from `data/correlated_signals/`, `data/narratives/`, `data/cross_asset/`, `data/macro/`, `data/onchain/`, `data/events/bus.jsonl` (anything that's append-only JSONL with timestamps). Uses an interval index (computed on first call, cached at `~/.cache/sapphire/timetravel/index.json`).
- `lib/timetravel/replay.py` (~350 LOC) — pure: takes a `SystemSnapshot` and replays the correlator + narrative engine against it. Returns what the system WOULD HAVE produced at that time given current code (vs what it DID produce, available from data/).
- `lib/timetravel/diff.py` (~250 LOC) — pure: compares "what was produced at time T" vs "what would be produced at T given current code". Surfaces drift. Example: "narrative engine v0.1.0 said BULL on BTC at T1; current v0.2.0 would say NEUTRAL → why?"
- `services/timetravel/build_index.py` — script to build the interval index across all `data/*.jsonl` time series.
- `plugins/claw-sapphire/tools/internal/timetravel.py` (~300 LOC) — stdin-JSON. Actions: `snapshot <at>`, `replay <at>`, `diff <at>`, `index-status`.
- `plugins/claw-sapphire/tools/timetravel.py` — shim.
- `tests/unit/test_timetravel_snapshot.py` (≥ 18 cases): correctness vs hand-computed snapshot, missing-data handling, time-zone discipline (everything UTC), out-of-range request.
- `tests/unit/test_timetravel_replay.py` (≥ 14 cases): mock the correlator + narrative engine; verify replay calls them with snapshot as input.
- `tests/unit/test_timetravel_diff.py` (≥ 12 cases).
- `plugins/claw-sapphire/tests/test_timetravel.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `timetravel`.
- `docs/products/timetravel-and-replay-0.1.0.md` (1500+ words).
- `docs/ops/timetravel-runbook.md` (1000+ words).

**PR title**: `feat(intelligence): time-travel + replay capability 0.1.0`

---

### LANE 4 — Source Quality Measurement (signal SNR, cross-source correlation, decay)

**Why it matters**: 9+ signal sources flowing into the correlator. We don't measure: (a) per-source signal-to-noise, (b) cross-source correlation (do 3 Telegram channels copy each other?), (c) source decay (was-good-now-spammy). Without this, blindly weighting all sources equally is leaving alpha on the table.

**Worktree + branch**: `~/Code/_worktrees/sapphire-source-quality` on `feat/source-quality-measurement`.

**Files**:
- `lib/source_quality/__init__.py`
- `lib/source_quality/snr.py` (~400 LOC) — pure: per-source historical signal-to-noise computation. Match each historical signal to its eventual outcome (when known). Compute precision, recall, F1. Output `SourceSNR`.
- `lib/source_quality/correlation.py` (~300 LOC) — pure: pairwise correlation of source signal timing + direction. Surfaces "Source A and Source B are 87% correlated → near-duplicates."
- `lib/source_quality/decay.py` (~250 LOC) — pure: rolling-window quality vs. historical baseline. Detects sources whose quality has degraded.
- `services/source_quality/run.py` (~250 LOC) — daily daemon: recompute SNR + correlation + decay per source, write `data/source_quality/<date>/report.json` + `data/source_quality/aggregates/rolling.json`.
- `services/dashboard/templates/pages/source_quality.html` — new dashboard page. Sections: SNR table, correlation heatmap, decay alerts.
- `services/dashboard/app.py` — `/source-quality` route + `/api/source-quality-snr`, `/api/source-quality-correlation`, `/api/source-quality-decay`.
- `plugins/claw-sapphire/tools/internal/source_quality.py` (~300 LOC) — stdin-JSON.
- `plugins/claw-sapphire/tools/source_quality.py` — shim.
- `tests/unit/test_source_quality_snr.py` (≥ 16 cases).
- `tests/unit/test_source_quality_correlation.py` (≥ 12 cases).
- `tests/unit/test_source_quality_decay.py` (≥ 10 cases).
- `tests/unit/test_dashboard_source_quality_routes.py` (≥ 8 cases).
- `plugins/claw-sapphire/tests/test_source_quality.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `source_quality`.
- `docs/products/source-quality-measurement-0.1.0.md` (1500+ words).
- `docs/ops/source-quality-runbook.md` (1000+ words).

**PR title**: `feat(intelligence): source quality measurement 0.1.0`

---

### LANE 5 — Walk-Forward Backtests + Regime Decomposition

**Why it matters**: Single-window backtests are 2010s-era. Modern quant shops do walk-forward with regime decomposition: train on T-window, test on T+1-window, advance, repeat. Plus regime-conditional Sharpe (does this strategy work in `risk_off` only?). The existing `lib/analytics/strategies.py` is left UNTOUCHED; we ADD `lib/analytics/walkforward/` alongside.

**Worktree + branch**: `~/Code/_worktrees/sapphire-walkforward` on `feat/walkforward-and-regime-backtests`.

**Files**:
- `lib/analytics/walkforward/__init__.py`
- `lib/analytics/walkforward/engine.py` (~600 LOC) — pure: walk-forward orchestrator. Takes a strategy + parameter grid + OHLCV + regime labels, runs train-then-test windows, returns `WalkforwardResult` with per-window metrics.
- `lib/analytics/walkforward/regime_decomp.py` (~350 LOC) — pure: decomposes strategy returns by regime label (consumes Tranche 4's cross-asset regime).
- `lib/analytics/walkforward/deflated_sharpe.py` — extend the existing `lib/analytics/deflated_sharpe.py` (read-only; add a thin wrapper here that handles the walk-forward case without modifying the source).
- `services/walkforward/build.py` — script: enumerates the 7 strategies × ~10 parameter grids, runs walk-forward over 90/180/365-day horizons, writes `data/backtests/walkforward/<date>/<strategy>.json`.
- `plugins/claw-sapphire/tools/internal/walkforward.py` — stdin-JSON.
- Shim, tests (≥ 60 cases total across engine/regime/deflated/plugin), product doc, runbook.

**Constraints**: ZERO modifications to `lib/analytics/strategies.py`, `lib/analytics/backtest.py`, `lib/analytics/risk_engine.py`. Adds alongside.

**PR title**: `feat(analytics): walk-forward + regime decomposition 0.1.0`

---

### LANE 6 — Inference Mesh Telemetry + Cost Analysis

**Why it matters**: 4-tier inference mesh (Windows GPU / Pi rari1+rari2 / Mac local / Kimi Cloud). We don't measure per-tier latency, throughput, cost, or token economics. A buyer asks "what's your inference cost per dollar of trade managed?" — the answer should be empirical, not vibes.

**Worktree + branch**: `~/Code/_worktrees/sapphire-inference-telemetry` on `feat/inference-mesh-telemetry`.

**Files**:
- `lib/inference_telemetry/__init__.py`
- `lib/inference_telemetry/aggregator.py` (~400 LOC) — pure: reads `~/.cache/sapphire/inference_proxy/calls.jsonl` (if exists; otherwise mock fixture path), computes per-tier latency p50/p99/p999, throughput (calls/min, calls/hour), error rate, token consumption, cost (USD where known).
- `lib/inference_telemetry/cost_model.py` (~250 LOC) — pure: cost model per tier. T1 (Windows GPU): electricity-only proxy, $0.001/inference. T2 (Pi): negligible. T3 (Mac local): electricity-only proxy. T4 (Kimi Cloud): per-token pricing from Moonshot's published rates.
- `lib/inference_telemetry/recommender.py` (~300 LOC) — pure: looks at observed tier mix vs. cost; surfaces "if you switched X→Y you'd save $Z/mo at current volume". Honest about caveats (latency tradeoff, tier failure, etc).
- `services/dashboard/templates/pages/inference_telemetry.html` — new panel.
- `services/dashboard/app.py` — routes + APIs.
- Tests, plugin tool, shim, registry append, product doc, runbook.

**PR title**: `feat(observability): inference mesh telemetry + cost analysis 0.1.0`

---

### LANE 7 — SEC Filings + Earnings Call Intelligence

**Why it matters**: Sapphire has 9+ signal sources but ZERO from primary corporate disclosures. SEC EDGAR is FREE and the most authoritative source for corporate signals. Earnings call transcripts (where free) are the highest-information-density company sources known.

**Worktree + branch**: `~/Code/_worktrees/sapphire-sec-and-earnings` on `feat/sec-filings-and-earnings-call-intel`.

**Files**:
- `lib/sources/sec_edgar.py` (~500 LOC) — adapter for SEC EDGAR API (`https://data.sec.gov/`). Pulls 8-K, 10-Q, 10-K filings for a curated ticker list (operator-supplied, defaults to empty + `~/.sapphire/sec_tickers.yaml`). Free; respects rate limits (10 req/sec hard).
- `lib/sources/earnings_calls.py` (~400 LOC) — adapter for free earnings call transcript sources. Start with public investor-relations RSS feeds (when available) + a stub for paid providers (NOT WIRED). Operator opt-in per ticker.
- `lib/sources/sec_classifier.py` (~300 LOC) — pure: classifies filings (e.g., 8-K Item 1.01 = material agreement; 8-K Item 4.01 = auditor change). Each gets a structured `FilingEvent` with severity/direction/asset hints.
- Adapter integration: extend `lib/correlator/sources.py` to register SEC filings + earnings calls as new source types.
- Tests (≥ 36 cases total), tool, shim, registry, product doc, runbook.

**Caps**: 10 req/sec hard; 5 tickers max per pull; cite SEC EDGAR docs URL.

**Constraints**: SEC's rate-limit + User-Agent requirements (must identify yourself); NO scraping companies that explicitly disallow.

**PR title**: `feat(intel): SEC filings + earnings call intelligence layer 0.1.0`

---

### LANE 8 — Chaos Engineering on Event Bus + Redis Fallback

**Why it matters**: The event bus has a Redis primary + JSONL fallback. We've never tested the failover under chaos. Modern systems do explicit chaos: kill Redis mid-stream, verify JSONL fallback engages, verify zero events lost.

**Worktree + branch**: `~/Code/_worktrees/sapphire-chaos-event-bus` on `feat/chaos-engineering-event-bus`.

**Files**:
- `lib/chaos/__init__.py`
- `lib/chaos/event_bus_chaos.py` (~400 LOC) — pure: chaos scenarios as test fixtures. Scenarios: redis-dies-mid-publish, redis-dies-mid-subscribe, jsonl-fallback-disk-full, redis-recovers-after-N-seconds, dual-write-mismatch.
- `tests/integration/test_event_bus_chaos.py` (≥ 18 cases): each scenario; mock Redis + filesystem entirely; assert zero events lost; assert ordering preserved post-recovery.
- `lib/chaos/fault_injector.py` (~250 LOC) — pure: fault-injection primitives that other chaos tests can reuse (clock skew, network partition, slow disk).
- `tests/unit/test_chaos_fault_injector.py` (≥ 12 cases).
- `docs/products/chaos-engineering-0.1.0.md` (1200+ words) — buyer-readable: what failure modes Sapphire formally tests.
- `docs/ops/chaos-engineering-runbook.md` (1000+ words).

**Constraints**: NEVER actually kills Redis on the operator's machine. All chaos is via mocked-fault-injection.

**PR title**: `feat(reliability): chaos engineering on event bus + redis fallback 0.1.0`

---

### LANE 9 — Tranche 6 Integration Pass

After all 8 build lanes merge, this PR wires them together. Examples:

1. **Lane 1 (property tests) ↔ Lane 2 (ADRs)**: ADR 0006 references property test catalog; index doc cross-links.
2. **Lane 1 ↔ Lane 5 (walk-forward)**: walk-forward engine has property-test invariants (deflated Sharpe is bounded, regime decomposition sums to 1.0).
3. **Lane 3 (time-travel) ↔ Lane 4 (source quality)**: source quality gets time-travel-aware ("what was the SNR profile 30 days ago?").
4. **Lane 4 (source quality) ↔ Lane 7 (SEC + earnings)**: SEC + earnings sources get measured by source quality immediately.
5. **Lane 6 (inference telemetry) ↔ Tranche 5 observability dashboard**: extend `/observability` with the inference telemetry panel.
6. **Lane 8 (chaos) ↔ Lane 2 (SLOs)**: SLO doc references chaos test results: "JSONL fallback recovers in < 5s under Redis-dies scenario per chaos test #3."
7. **README** refresh for the final test count + tool registry count.

**PR title**: `feat(excellence): tranche-6 integration pass`

---

## 4. Verification protocol

Per lane:
```bash
ruff check .
/usr/local/bin/python3 -m pytest <NEW_TEST_FILES> -q --tb=short
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

`0 FAIL` mandatory. Run unit + plugin pytest blocks SEPARATELY.

---

## 5. Merge protocol

Use `~/Code/Sapphire/scripts/ops/sapphire_safe_merge.sh <PR>`. Fallback: explicit `-t '<title> [skip ci]'`.

---

## 6. Closeout deliverable

After all 9 PRs merge, `docs/handoffs/tranche-6-excellence-2026-04-30-report.md`:
1. Final main SHA + open PR/issue counts.
2. Per-lane status with key metrics (mutation kill rate, ADR count, walk-forward Sortino spread, inference-cost recommendation savings %, etc.).
3. Verification at handoff.
4. Operator-owed actions.
5. Compound-edge evidence (each of the 5 buyer-questions answered concretely).
6. Tranche 7 backlog suggestion.

Update `~/.claude/projects/-Users-aribs/memory/MEMORY.md` with one line.

---

## 7. Posture reminders

- **Quality over quantity.**
- **Honest framing**.
- **Provenance everywhere**.
- **Trading critical path is sacred** — Lane 5 reads `lib/analytics/strategies.py` but does NOT modify it.
- **The Hyperliquid live-executor stash** at `git stash@{0}` and `stash@{1}` is OFF-LIMITS.
- **No real customer payments**. Tranche 5's customer surface stays mock-default.
- **Cross-lane awareness.**
- **Integration-pass PR is non-optional.**

This is the tranche where Sapphire stops being **"a polished prototype"** and becomes **"an institutional-grade intelligence platform with documented rigor."** Buyer's diligence team has 5 questions; this tranche answers all 5 with code + docs + measurements.

Now go.
