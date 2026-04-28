# Codex Megaprompt — Tranche 4 — Intelligence Deep Work — 2026-04-28

> **Operator usage**: paste this entire document into a fresh Codex session AFTER Tranche 3 has fully landed (verify with the Pre-Flight in §2 below). This is a deep work session — fewer ceremony, more substance, more web research, more cross-system synthesis. Codex MUST read top-to-bottom before any tool calls.

---

## 0. Mission

You are Codex, working with **full autonomy granted by the operator (Ari)** for a deep multi-hour intelligence-deepening tranche. This is **Tranche 4** in a multi-day acquisition push:

- **Tranche 1** (2026-04-28 morning): pytest collection, repo hygiene, BacktestEngine adapter — 12 PRs.
- **Tranche 2** (2026-04-28 afternoon/evening): Wave 4 acquisition surfaces — 23 PRs.
- **Tranche 3** (2026-04-28 night through morning of 2026-04-29): correlation engine, observability dashboard, foundry ontology expansion, acquirer microsite, ramp memo, safe-merge guardrail, dossier 0.2.0, health-context helper — ≥ 8 PRs.
- **Tranche 4** (NOW — this prompt): the layer above. Tranche 3 shipped capability; **Tranche 4 ships compound edge**.

The mental model for Tranche 4: **From Built to Compound**. Tranche 3 wired all the signal feeds into a single `edge_score`. Tranche 4 takes those correlated signals and produces (a) **narrative synthesis**, (b) **regime intelligence**, (c) **regulatory + macro context**, (d) **adversarial defenses**, and (e) **deep external research** that grounds the system's view of itself in the broader market and competitive landscape. World-class intelligence systems do this — Two Sigma, Renaissance, Citadel, Bloomberg Terminal, Palantir Foundry. Sapphire should stand alongside them in this tranche.

This is a **deep work session**. Lanes are bigger than Tranche 3's. Some lanes are pure deep web research with no code at all. Some lanes mix research + build. **Quality over speed**. A polished single deliverable per lane is worth more than three shallow ones.

If your runtime supports parallel sub-agents, dispatch all 8 lanes concurrently. If not, do them sequentially in the order listed (highest-impact first).

---

## 1. Non-negotiable constraints

These bind every commit, every PR, every action:

1. **No-spend posture is sacred.** Every commit message ends with `[skip ci]`. Every `gh pr merge --squash` MUST pass `-t '<title> [skip ci]'` explicitly. After every merge, run `gh run list --limit 5` and cancel anything queued.
2. **Don't touch the trading critical path** (`services/alpha/`, `lib/portfolio/robinhood.py`, `lib/trading/`, `lib/analytics/risk_engine.py`, `lib/analytics/strategies.py`, `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`, `services/webhook/`, `contracts/`). CODEOWNERS-gated.
3. **Stay out of Tranche 3's footprint** (read state at start in §2 — anything Tranche 3 added is OFF-LIMITS for this tranche). Specifically: do not modify `lib/correlator/`, `lib/observability/`, `services/correlator/`, `lib/foundry/ingestion.py`, `web/acquirer/`, `lib/agents/health_context.py`, `scripts/ops/sapphire_safe_merge.{sh,py}`, or any test file Tranche 3 added. Extend by ADDING new modules that consume Tranche 3's outputs.
4. **Web research lanes (Lane 4, Lane 5)**: use web-fetch tools available to you. ALWAYS cite primary sources (URLs, dates, authors). NEVER fabricate quotes or statistics. If a source is paywalled or unreachable, document the gap.
5. **Watch for the fixture-clock vs impl-clock date-flake pattern.** Patched in #377 and #394; will recur. Anytime a test uses `datetime.now()` against an impl that takes a `now` arg, monkey-patch with the FrozenDatetime template.
6. **Do not touch satellite repos.** Sapphire monorepo only.
7. **Secrets are read-only and live-mode-only.** Mirror the `gemini_ooda` / `vertex_eval` / `vertex_gecko_embedder` pattern: secrets only loaded when env-flag-gated live path triggers. Never logged.
8. **Dry-run is the default for any new external-API surface.** New caps + counters under `~/.cache/sapphire/<tool>/`.
9. **Provenance envelopes on all generated artifacts.** `lib/core/provenance.py`.
10. **No README test counts during multi-lane work.** Closeout PR updates README once.
11. **No new top-level dependencies** unless the lane explicitly authorizes them. Lanes 6 + 7 are the only lanes this tranche authorized to add new prod deps (specifically: `glassnode-api>=0.x` and `feedparser>=6.0` already pinned). Everything else stdlib + already-pinned.
12. **Worktree-per-lane.** Each lane creates `~/Code/_worktrees/sapphire-<branch>`. Clean up worktrees when their PR merges.
13. **Open PR but DO NOT auto-merge** unless local verification is green: ruff, both pytest blocks (separately), `validate_tool_registry.py`, `production_readiness_sweep.py --no-external` (`0 FAIL`). When green, admin-squash-merge with explicit `-t "<title> [skip ci]"`.

---

## 2. Pre-flight + state at start

**BEFORE anything else**: verify Tranche 3 has fully landed and the canonical state is clean.

```bash
cd ~/Code/Sapphire
git fetch --all --quiet
git rev-parse --short HEAD
gh pr list --state open --json number,title --jq 'length'      # expect: 0 (or near-0; describe each)
gh issue list --state open --json number --jq 'length'         # informational, list any
/usr/local/bin/python3 -m pytest tests/unit/ -q                # expect: ≥ 4,300 passed
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q  # expect: ≥ 290 passed
/usr/local/bin/python3 scripts/validate_tool_registry.py       # expect: registry ≥ 42, errors=0
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -3   # expect: 0 FAIL

# Confirm Tranche 3 surfaces exist
ls lib/correlator/                                              # expect: __init__.py, engine.py, sources.py, scoring.py
ls services/correlator/                                         # expect: run.py, etc
ls services/dashboard/templates/pages/observability.html        # expect: file exists
ls web/acquirer/                                                # expect: dir exists with index.html
ls scripts/ops/sapphire_safe_merge.sh                           # expect: file exists
ls docs/products/live-trading-ramp-memo.md                      # expect: file exists
ls docs/security/kill-switch-invariants.md                      # expect: file exists
ls lib/agents/health_context.py                                 # expect: file exists
```

If any of those are missing, **stop and write a short pre-flight report**: which Tranche 3 deliverables haven't landed, why you're proceeding without them, what you'll do differently.

**Reference reading** (skim before any lane):
- `docs/handoffs/codex-megaprompt-tranche-3-2026-04-28.md` — the previous megaprompt; structurally similar.
- `docs/handoffs/codex-megaprompt-tranche-3-2026-04-29-report.md` (or wherever Tranche 3's closeout lives) — what just landed.
- `docs/handoffs/claude-night-session-2026-04-28-report.md` — Tranche 2 by Claude.
- `lib/correlator/engine.py` — the correlation engine your synthesis will sit on top of.
- `lib/observability/aggregator.py` — observability data your dashboards will join.
- `plugins/claw-sapphire/tools/internal/{gemini_ooda,vertex_eval,telegram_intel,hyperliquid,signal_correlator}.py` — canonical tool patterns.
- `docs/products/*.md` — every existing product doc; understand the surface.
- `infra/tool-registry.yaml` — should be ≥ 43 entries after Tranche 3.

---

## 3. Lanes

**Eight lanes. Each lands in a single PR. Order matters: higher-impact first.** This is deep work — most lanes are 1500+ LOC, 50+ tests, 2000+ words of docs.

---

### LANE 1 — LLM Narrative Synthesis Engine on Top of `signal_correlator`

**Why it matters**: Tranche 3's `signal_correlator` produces a deterministic `edge_score` plus a `corroborated_by` array. That's a number, not a narrative. World-class intelligence systems produce **prose theses** that articulate WHY the edge is there, what would invalidate it, what the next signal to watch is, and what the implied position is. Bloomberg's Intelligence team writes morning notes; Sapphire's narrative engine produces a similar thing — automatically, bounded, dry-run-default, provenance-stamped.

This is THE lane that turns Sapphire from "system that emits scores" into "system that explains the market in narrative form."

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-narrative-synthesis` on `feat/narrative-synthesis-engine`.

**Templates to read first**:
- `lib/correlator/engine.py` — the input.
- `plugins/claw-sapphire/tools/internal/gemini_ooda.py` — bounded LLM tool template.
- `plugins/claw-sapphire/tools/internal/vertex_eval.py` — rubric scoring; reuse the structural-validity / actionability rubric concepts.
- `lib/intel/sovereign_thesis.py` — existing thesis aggregation.

**Files**:
- `lib/synthesis/__init__.py`
- `lib/synthesis/narrative_engine.py` (~700 LOC) — pure logic + bounded LLM call. Takes a `CorrelatedSignal` (Tranche 3's output), produces a `NarrativeThesis` dataclass with: `thesis_one_paragraph`, `evidence_bullets: list[str]`, `counter_thesis_one_paragraph`, `invalidators: list[str]`, `next_signal_to_watch: str`, `implied_position: Literal["long_strong", "long_mild", "neutral", "short_mild", "short_strong", "no_position"]`, `confidence: float ∈ [0, 1]`, `caveat_block: str`, `provenance_envelope: dict`. Live mode requires `SAPPHIRE_NARRATIVE_LIVE=1` AND a Gemini key in `~/.sapphire/secrets.env` AND prompt passes sensitivity gate. Dry-run default emits a deterministic mock derived from the input.
- `lib/synthesis/prompts.py` (~200 LOC) — the canonical prompts (system, user-template, rubric). Versioned. NEVER inline-edit live prompts; bump `PROMPT_VERSION` when changing.
- `lib/synthesis/rubric.py` (~250 LOC) — pure scoring of a generated narrative (mirrors vertex_eval rubric: structural_validity, actionability, citation_density, internal_consistency, hedging_appropriateness). Used to gate quality before the narrative is published.
- `services/synthesis/run.py` (~350 LOC) — async daemon. Polls correlator output every 30 minutes (configurable), generates a narrative for each `(symbol, timeframe)` pair where the edge_score has changed > 0.1 since last narrative, scores it via rubric, publishes to event bus on `narrative.thesis.generated`, writes to `data/narratives/<date>/theses.jsonl` with provenance.
- `services/synthesis/launchagent/com.sapphire.narrative-synthesis.plist.template` (do NOT install).
- `plugins/claw-sapphire/tools/internal/narrative_synthesis.py` (~400 LOC) — stdin-JSON tool. Actions: `synthesize-once`, `latest`, `history`, `rubric-score`, `status`. Mirrors `gemini_ooda` shape.
- `plugins/claw-sapphire/tools/narrative_synthesis.py` — 3-line shim.
- `tests/unit/test_synthesis_narrative_engine.py` (≥ 25 cases): dry-run default, live env gate, sensitivity gate, all 6 implied_position values reachable, rubric gating drops low-quality narratives, cache short-circuit.
- `tests/unit/test_synthesis_rubric.py` (≥ 18 cases): each rubric dimension's boundaries, idempotence, monotonicity.
- `tests/unit/test_synthesis_prompts.py` (≥ 8 cases): prompt versioning, no PII leaks, deterministic templating.
- `services/synthesis/tests/test_synthesis_run.py` (≥ 10 cases) OR `tests/unit/test_synthesis_run.py`.
- `plugins/claw-sapphire/tests/test_narrative_synthesis.py` (≥ 12 plugin tests).
- `infra/tool-registry.yaml` — append `narrative_synthesis` under "AI complement".
- `docs/products/narrative-synthesis-0.1.0.md` (1500+ words) — buyer-facing doc with a full worked example narrative for BTC.
- `docs/ops/narrative-synthesis-runbook.md` (1500+ words) — operator runbook.

**Caps** (mirror gemini_ooda):
- `MAX_OUTPUT_TOKENS_HARD = 6144` (narratives are longer than OODA packets)
- `MAX_INPUT_CHARS_HARD = 18_000`
- `MAX_CALLS_PER_HOUR = 6` (narratives are expensive)
- `MAX_TOKENS_PER_MONTH = 750_000`
- `MIN_RUBRIC_SCORE_TO_PUBLISH = 0.7` (don't emit garbage)

**PR title**: `feat(synthesis): llm narrative thesis engine 0.1.0`

---

### LANE 2 — Cross-Asset Correlation Matrix + Regime Detection

**Why it matters**: Sapphire correlates SIGNALS across feeds. It does not yet correlate ASSETS across markets. A real intelligence system shows you when BTC's correlation to SPY breaks down (regime shift), when gold correlation to USD inverts (crisis signal), when Hyperliquid imbalance leads spot by 4 hours (predictive lead). This is the analytics layer every quant desk has and Sapphire is missing.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-cross-asset-correlation` on `feat/cross-asset-correlation-and-regime`.

**Templates to read first**:
- `lib/analytics/correlation.py` (if exists — search) — existing correlation primitive.
- `lib/analytics/regime.py` (if exists) — existing regime detection.
- `lib/analytics/forecast.py` — reconciliation pattern.
- `services/dashboard/app.py` — routes for the new dashboard panel.

**Files**:
- `lib/cross_asset/__init__.py`
- `lib/cross_asset/correlation_matrix.py` (~500 LOC) — pure: takes a dict `{asset: ohlcv_series}` and returns a `CorrelationMatrix` with rolling Pearson + Spearman + Kendall on configurable windows (24h, 7d, 30d). Surfaces correlation **breakdown events** (when a pair's rolling-7d correlation moves > 2 stdevs from its trailing 90d mean).
- `lib/cross_asset/regime_detector.py` (~400 LOC) — pure: uses GMM (existing `lib/analytics/regime.py` if it has GMM) OR a simple HMM on the correlation matrix to label market regimes (`risk_on_correlated`, `risk_on_decorrelated`, `risk_off_flight_to_dollar`, `crisis_correlation_spike`, `regime_uncertain`). Emits a `RegimeLabel` per timestamp.
- `lib/cross_asset/sources.py` (~300 LOC) — adapters that pull OHLCV for: BTC/ETH/SOL (from existing OpenBB `:6900` provider), SPY/QQQ (yfinance via OpenBB), Gold (XAUUSD via OpenBB), DXY (USD index via OpenBB), CNY/JPY (forex via OpenBB), Hyperliquid (from Tranche 2's `services/hyperliquid/`), VIX (yfinance). All cached; no live network in tests.
- `services/cross_asset/run.py` (~250 LOC) — daemon: every hour pulls latest OHLCV, recomputes matrix + regime label, publishes to event bus on `regime.shift.detected` and `correlation.breakdown`, writes to `data/cross_asset/<date>/matrix.json` + `regimes.jsonl` with provenance.
- `services/dashboard/templates/pages/cross_asset.html` — new dashboard page. Sections: Live correlation heatmap (D3.js or pure SVG), regime label + 30-day history strip, breakdown events table, lead/lag analysis.
- `services/dashboard/app.py` — add `/cross-asset` route + `/api/cross-asset-matrix`, `/api/cross-asset-regime`, `/api/cross-asset-breakdowns` endpoints.
- `plugins/claw-sapphire/tools/internal/cross_asset_intel.py` (~300 LOC) — stdin-JSON tool. Actions: `matrix`, `regime`, `breakdowns`, `lead-lag`, `status`.
- `plugins/claw-sapphire/tools/cross_asset_intel.py` — shim.
- `tests/unit/test_cross_asset_correlation_matrix.py` (≥ 22 cases): rolling-window correctness, NaN handling, window-too-short edge case, breakdown threshold, multi-method (Pearson/Spearman/Kendall) consistency, determinism.
- `tests/unit/test_cross_asset_regime_detector.py` (≥ 18 cases): each labeled regime reachable from synthetic data, transition smoothing, handles gaps in input.
- `tests/unit/test_cross_asset_sources.py` (≥ 12 cases): all adapters mock cleanly, no live calls.
- `tests/unit/test_dashboard_cross_asset_routes.py` (≥ 10 cases).
- `plugins/claw-sapphire/tests/test_cross_asset_intel.py` (≥ 10 plugin tests).
- `infra/tool-registry.yaml` — append `cross_asset_intel`.
- `docs/products/cross-asset-correlation-0.1.0.md` (1200+ words).
- `docs/ops/cross-asset-runbook.md` (1500+ words).

**Caps**:
- `MAX_ASSETS_HARD = 24`
- `MAX_WINDOW_DAYS = 365`
- `MIN_OBSERVATIONS_PER_WINDOW = 30`

**PR title**: `feat(intel): cross-asset correlation matrix + regime detection 0.1.0`

---

### LANE 3 — Regulatory + Macro Intelligence Daemon

**Why it matters**: Trading signals are noise without macro context. FOMC meetings move markets; CFTC enforcement actions move crypto specifically; Treasury auctions move yields; ECB statements move FX. Sapphire currently ignores all of this. This lane builds the daemon that watches official calendars and publications and tags every Sapphire signal with structured macro context.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-macro-intel` on `feat/regulatory-macro-intel`.

**Sources to ingest** (use stdlib + `feedparser`; no new deps):
- **Federal Reserve**: `https://www.federalreserve.gov/feeds/press_all.xml` (RSS)
- **FOMC calendar**: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` (HTML scrape; sitemap fallback)
- **CFTC press releases**: `https://www.cftc.gov/PressRoom/PressReleases.rss`
- **SEC press releases**: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&count=40&output=atom`
- **Treasury auction calendar**: `https://www.treasurydirect.gov/auctions/auctions-query/` (parse the auction-results page)
- **BLS economic releases**: `https://www.bls.gov/feed/news_release/empsit.rss` and similar
- **ECB**: `https://www.ecb.europa.eu/rss/press.html`
- **BIS**: `https://www.bis.org/list/press_releases/index.rss`

**Files**:
- `lib/macro/__init__.py`
- `lib/macro/sources.py` (~600 LOC) — one async fetcher class per source above. Each implements `pull(since: datetime) -> list[MacroEvent]`. ALL parsing pure (no LLM). Caches per-source under `~/.cache/sapphire/macro/<source>/`.
- `lib/macro/classifier.py` (~300 LOC) — pure: takes a `MacroEvent` (title, body, source, date) and tags it with: `category` (monetary_policy / regulatory_enforcement / data_release / treasury_auction / international / other), `assets_likely_affected` (BTC, ETH, SOL, equities, gold, USD, EUR, etc.), `expected_impact_severity` (low / medium / high / extreme), `direction_hint` (hawkish / dovish / neutral / mixed). Heuristic-based with a clear threshold table; no LLM.
- `lib/macro/calendar.py` (~250 LOC) — pure: maintains a forward-looking calendar of scheduled events (FOMC dates, payrolls, treasury auctions). Returns "next scheduled event for asset X" and "events in next N hours."
- `services/macro_intel/run.py` (~350 LOC) — daemon: every 15 minutes pull all sources, classify, publish to event bus on `macro.event.detected` + `macro.calendar.window_opening`, write to `data/macro/<date>/events.jsonl` + `calendar.jsonl` with provenance.
- `services/macro_intel/launchagent/com.sapphire.macro-intel.plist.template`.
- `plugins/claw-sapphire/tools/internal/macro_intel.py` (~400 LOC) — stdin-JSON tool. Actions: `recent`, `calendar`, `next-event-for-asset`, `pull-once` (one-shot).
- `plugins/claw-sapphire/tools/macro_intel.py` — shim.
- `tests/unit/test_macro_sources.py` (≥ 24 cases): one per source, all HTTP/feedparser mocked, parsing of historical fixture XML/HTML.
- `tests/unit/test_macro_classifier.py` (≥ 16 cases): each category + severity + direction reachable from real-historical fixture titles (e.g., "FOMC Holds Rates" → monetary_policy + medium + dovish).
- `tests/unit/test_macro_calendar.py` (≥ 10 cases): forward-looking ordering, window queries.
- `plugins/claw-sapphire/tests/test_macro_intel.py` (≥ 8 cases).
- `infra/tool-registry.yaml` — append `macro_intel`.
- `docs/products/macro-intel-0.1.0.md` (1200+ words).
- `docs/ops/macro-intel-runbook.md` (1500+ words; including a curated source-credibility note: which sources are first-party, which we trust, which we treat as confirmation-only).

**Caps**:
- `MAX_PULLS_PER_HOUR_PER_SOURCE = 4` (don't hammer official sites)
- `MAX_EVENTS_PER_PULL = 100`
- `MAX_FORWARD_CALENDAR_DAYS = 90`

**Constraints**:
- **No live calls in tests.** Use historical fixture XML/HTML files committed under `tests/fixtures/macro/`.
- **Respect robots.txt** for HTML scrapes; default User-Agent identifies Sapphire and provides a contact.
- **Cite the source URL** in every event's metadata so the dashboard can deep-link.

**PR title**: `feat(intel): regulatory + macro intelligence daemon 0.1.0`

---

### LANE 4 — Competitive Landscape Deep Research Memo (PURE WEB RESEARCH)

**Why it matters**: Sapphire's acquisition narrative needs to know how it compares to the existing world. A buyer's diligence team WILL ask "how does this differ from Foundry / Cortex / Bloomberg / Two Sigma?" Having a written answer that's grounded in primary sources puts you ahead of every founder who hand-waves this question. This lane is a 2,500+ word research deliverable.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-competitive-landscape` on `docs/competitive-landscape-2026-04-28`.

**This lane has NO code**. It is a deep web research deliverable.

**Targets to research** (hit primary sources where possible):

1. **Palantir Foundry** — current capabilities (especially "Ontology", "AIP" / Artificial Intelligence Platform), recent product launches in 2025–2026, partner ecosystem (DoD, Anthem, Airbus, Wendy's, JPM), pricing model (per-seat vs platform), recent corp-dev signals (acquisitions of small data/AI startups, partnership announcements). Sources: palantir.com/blog, sec.gov filings (last two 10-Q + most recent 10-K + 8-K filings), Palantir investor day decks if linked publicly.
2. **Robinhood Cortex** — public statements about their AI/intelligence platform, the IPO of Robinhood Crypto's Bitstamp acquisition's intelligence components, public blog posts about ML in their stack, recent hires from Bloomberg / Bridgewater / Two Sigma.
3. **Bloomberg Terminal Intelligence** — Terminal AI features, BloombergGPT (the 2023 paper + any 2025–2026 updates), Bloomberg Intelligence vs Bloomberg Terminal's signals, the partnership with Anthropic announced if any.
4. **Two Sigma, Renaissance, Citadel** — public-facing thinking on multi-source intelligence. Don't fabricate insider info; rely on (a) Renaissance Medallion-related public commentary (Jim Simons interviews), (b) Two Sigma's published research papers on factor decomposition + alt data, (c) Citadel's public hiring patterns + Ken Griffin's letters.
5. **Open-source quant + AI agent frameworks** — LangChain agents for finance, CrewAI, AutoGen, the Anthropic Claude Code + Codex pattern itself. What's the state of "autonomous agents that produce theses"?
6. **The recent corp-dev landscape** — any 2025–2026 acquisitions of small-to-mid quant/intelligence startups by the larger players? Pricing comps, multiples, what was acquired (talent vs IP vs product)?

**Output**: a single 2500+ word memo at `docs/competitive/landscape-2026-04-28.md`, structured as:

1. **Executive summary** — one paragraph: who's the field, where Sapphire fits, the one-line differentiator.
2. **Per-target sections** — one per target above. Cite at least 3 primary URLs per target. Quote conservatively — paraphrase mostly.
3. **Sapphire's positioning matrix** — a 2D table: rows = capabilities (multi-source signal correlation, narrative synthesis, regulatory ingestion, customer-facing dashboards, on-chain depth, on-DEX intel, etc.), columns = competitors. Cell values: `✓` / `✗` / `partial` / `unknown`.
4. **What Sapphire genuinely does that no one else does** — be honest. Probably: claw-code-foundation + Telegram-first ops + bounded-LLM-narrative + per-tenant provenance envelopes. State this clearly.
5. **What Sapphire should NOT try to compete on** — table-stakes for the big players (e.g., real-time tick data infra; institutional broker APIs; macro economist headcount). State this clearly.
6. **Open questions** — the things primary research couldn't answer. Be honest about gaps.
7. **Acquisition pitch implications** — which competitor's diligence team would Sapphire's narrative resonate most with, and why. Specific reasoning for Palantir vs. Robinhood vs. a smaller acquirer.

**Verification**:
- Word count ≥ 2500
- Every cited URL resolves (use a `WebFetch`-style check)
- No fabricated quotes (Codex MUST verify each pull-quote against the source)
- Provenance envelope sidecar at `docs/competitive/landscape-2026-04-28.md.envelope.json`
- File MUST commit cleanly with `[skip ci]`

**Constraints**:
- **Honesty over hype**. If a competitor outclasses Sapphire on a dimension, say so.
- **No fabricated insider info**. Public sources only.
- **Date-stamp every claim**. Markets move; an "as-of-2026-04-28" tag is mandatory on each major claim.

**PR title**: `docs(competitive): landscape research 2026-04-28`

---

### LANE 5 — Adversarial / Red-Team Intelligence Defense Layer

**Why it matters**: Tranche 3 shipped a multi-source signal correlation engine. The threat surface grew with it. A sophisticated adversary could inject false signals into Telegram channels, manipulate Hyperliquid book imbalance with wash trades, post fake threat intel to public feeds, or feed Sapphire prompts designed to skew the narrative engine's output. World-class intelligence systems have **adversarial defenders** sitting alongside the signal aggregators. This lane builds them. **Half research, half code.**

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-adversarial-defense` on `feat/adversarial-defense-layer`.

**Research deliverable** (45% of this lane):
- `docs/security/adversarial-intelligence-threat-model-2026-04-28.md` (2000+ words). Sections:
  1. **Trust boundary** — what does Sapphire trust on input?
  2. **Per-source attacker profile** — for each of the 9 signal feeds (TradingView webhook, Telegram intel, Hyperliquid feed, threat-intel sweep, sovereign-thesis convergence, Kronos forecast, TA scanner, narrative synthesis, regulatory/macro intel from Lane 3): who could lie to it, how cheaply, and what they'd gain.
  3. **Historically-successful manipulation patterns** — wash trading (cite real cases), oracle manipulation (e.g., Mango Markets 2022, Cream V1), bot-pumped Telegram channels, false flag threat intel, prompt injection (cite recent academic work + real-world incidents). Link primary sources.
  4. **Sapphire's existing defenses** — what we already do well (sensitivity classifier, fail-closed allowlist, rate limits, provenance envelopes, dry-run defaults, kill-switch invariants).
  5. **Per-attack defense gaps** — what's still vulnerable.
  6. **Acquisition relevance** — buyers care about this. Make it readable for a corp-dev CTO.

**Code deliverable** (55% of this lane):
- `lib/security/adversarial_detectors.py` (~600 LOC) — pure detectors:
  - `WashTradeDetector` for Hyperliquid (looks for self-trading patterns in time-stamp-clustered fills).
  - `BotPumpedChannelDetector` for Telegram intel (looks for: sudden engagement spikes, identical-template messages, account-age + message-count anomalies).
  - `OracleAnomalyDetector` for cross-asset (price moves > N stdev from cross-exchange median in < 60s).
  - `PromptInjectionDetector` for narrative synthesis input (regex + heuristic classifier; blocks prompts containing "ignore previous instructions" or signal-data-as-instructions patterns).
  - `FalseFlagThreatIntelDetector` (checks new threat-intel claims against CISA KEV ground truth before propagating).
- `lib/security/adversarial_telemetry.py` (~250 LOC) — emits structured `adversarial.detection` events to event bus when ANY detector fires; never silently squashes input.
- `services/adversarial/run.py` (~250 LOC) — daemon: subscribes to all 9 signal-feed event topics, runs detectors, emits telemetry, optionally quarantines suspect signals (configurable; default OFF — flag-only).
- `tests/unit/test_adversarial_wash_trade_detector.py` (≥ 16 cases): synthetic wash patterns trip detector; legitimate trading does NOT.
- `tests/unit/test_adversarial_bot_pumped_detector.py` (≥ 14 cases).
- `tests/unit/test_adversarial_oracle_detector.py` (≥ 12 cases).
- `tests/unit/test_adversarial_prompt_injection.py` (≥ 22 cases): real prompt-injection patterns from public datasets (cite OWASP LLM Top 10, recent papers).
- `tests/unit/test_adversarial_false_flag_threat_detector.py` (≥ 8 cases).
- `tests/unit/test_adversarial_telemetry.py` (≥ 8 cases).
- `infra/tool-registry.yaml` — append (if exposed as a plugin tool — author's call; can also stay service-only).
- `docs/products/adversarial-defense-0.1.0.md` (1500+ words) — buyer-facing.

**Constraints**:
- **No false positives during test runs**. Each detector's test corpus must include a "clean" baseline that the detector ignores.
- **Detectors emit telemetry; do NOT modify signals upstream by default**. Quarantining is opt-in via `SAPPHIRE_ADVERSARIAL_QUARANTINE=1`.
- **Cite real cases** in the threat-model doc. Don't invent.

**PR title**: `feat(security): adversarial intelligence defense layer 0.1.0`

---

### LANE 6 — On-Chain Intelligence Deepening (Glassnode + Santiment + ETH/SOL chain)

**Why it matters**: `lib/chain/` exists with `coinmetrics.py`, `intelligence.py`, `sources.py`, plus on-chain providers under `lib/chain/providers/`. They're partially implemented or mocked. **Real institutional crypto intelligence** uses Glassnode metrics (HODL waves, NUPL, MVRV, SOPR, Net Realized Profit/Loss, Long-Term Holder supply), Santiment (social volume, age-consumed, network growth), and direct chain data (active addresses, fee distribution, TVL changes). This lane wires up the real providers and makes them first-class signal sources for the correlation engine.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-onchain-deep` on `feat/onchain-intelligence-deepening`.

**Templates to read first**:
- `lib/chain/providers/` — see what's stubbed.
- `lib/chain/coinmetrics.py` — fully test-covered (Tranche 2 #382 added 32 cases).
- `plugins/claw-sapphire/tools/internal/gemini_ooda.py` — env-gated live mode pattern.

**Files**:
- `lib/chain/providers/glassnode.py` (full impl, ~400 LOC) — real Glassnode API client. Live behind `SAPPHIRE_GLASSNODE_LIVE=1` AND `GLASSNODE_API_KEY` in `~/.sapphire/secrets.env`. Implements: HODL waves, NUPL, MVRV-Z, SOPR, LTH supply, ETF balance proxies. Caps + counters under `~/.cache/sapphire/glassnode/`.
- `lib/chain/providers/santiment.py` (full impl, ~350 LOC) — real Santiment GraphQL client. Live behind `SAPPHIRE_SANTIMENT_LIVE=1` + `SANTIMENT_API_KEY`. Implements: social volume, social dominance, age-consumed, network growth.
- `lib/chain/providers/eth_node.py` (~250 LOC) — extends the existing `robinhood_chain` pattern but for Ethereum Mainnet via web3.py. Reads gas, block production, top-N pending tx mempool, ETF unstaking queue. Live behind `SAPPHIRE_ETH_NODE_LIVE=1` + RPC URL env var.
- `lib/chain/providers/sol_node.py` (~250 LOC) — Solana RPC. TPS, validator status, top stake delegations.
- `lib/chain/aggregator.py` (~400 LOC) — pure aggregator that joins all on-chain providers + coinmetrics into a single `OnChainSnapshot` dataclass per (asset, timestamp). Powers the correlator's on-chain source adapter.
- `services/onchain_intel/run.py` (~250 LOC) — daemon: every 30 minutes pull from all enabled providers, aggregate, publish `onchain.snapshot.updated`, write `data/onchain/<date>/snapshots.jsonl` with provenance.
- `services/onchain_intel/launchagent/com.sapphire.onchain-intel.plist.template`.
- `plugins/claw-sapphire/tools/internal/onchain_intel.py` (~350 LOC) — stdin-JSON tool. Actions: `snapshot`, `metric` (specific metric lookup), `regime` (on-chain regime classification — accumulation / distribution / capitulation / euphoria), `status`.
- `plugins/claw-sapphire/tools/onchain_intel.py` — shim.
- `tests/unit/test_chain_glassnode.py` (≥ 18 cases): mock the SDK, env-flag gating, caps, fallback to mock when key missing, schema validation.
- `tests/unit/test_chain_santiment.py` (≥ 14 cases).
- `tests/unit/test_chain_eth_node.py` (≥ 12 cases).
- `tests/unit/test_chain_sol_node.py` (≥ 10 cases).
- `tests/unit/test_chain_aggregator.py` (≥ 16 cases).
- `plugins/claw-sapphire/tests/test_onchain_intel.py` (≥ 12 cases).
- `infra/tool-registry.yaml` — append `onchain_intel`.
- `docs/products/onchain-intelligence-0.2.0.md` (1500+ words; bump prior 0.1 if any to 0.2).
- `docs/ops/onchain-intel-runbook.md` (1500+ words).

**Caps** (per-provider):
- `MAX_CALLS_PER_HOUR = 60`
- `MAX_TOKENS_PER_DAY = 100_000`
- `MAX_BACKFILL_DAYS = 730`

**Constraints**:
- **Tests use ZERO live calls.** Every external SDK is mocked.
- **Operator must opt-in to live** per provider via env flag + secrets file.
- **Glassnode + Santiment have free tiers** but are rate-limited; document the bounded posture clearly.

**PR title**: `feat(chain): on-chain intelligence deepening (glassnode + santiment + nodes) 0.2.0`

---

### LANE 7 — News-Event Impact Modeling (Historical Backtest + Lookup Table)

**Why it matters**: When the FOMC raises rates, BTC tends to drop in the next 6 hours but recover in 48; when an ETF gets approved, BTC tends to spike in the next 4 hours; when an exchange gets hacked, the affected token drops 30-60%. Sapphire should KNOW these patterns. This lane builds the **historical event-impact lookup**: when event X (from Lane 3's macro feed) happens, what's the empirical historical reaction across BTC/ETH/SOL/SPY/Gold? Output: a table the narrative engine and correlator can consult.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-event-impact-model` on `feat/event-impact-modeling`.

**Templates to read first**:
- `lib/analytics/backtest_engine.py` — backtest primitive.
- `lib/macro/sources.py` — macro events (Lane 3 produces; if Lane 3 hasn't landed when you start this, write source-fetch directly here for FOMC + ETF + hack events as a self-contained subset).

**Files**:
- `lib/event_impact/__init__.py`
- `lib/event_impact/event_corpus.py` (~400 LOC) — pure: maintains a curated corpus of historical events at `data/event_corpus/events.jsonl`. Categories: FOMC decisions (rate up/down/hold), ETF approvals (BTC/ETH spot), exchange hacks (named: Mt Gox, Bitfinex 2016, FTX, Mango, Cream, etc.), regulatory enforcement actions (SEC v Coinbase, BinanceJP, etc.), macro shocks (COVID March 2020, Russia 2022, SVB 2023). Each event has timestamp + category + sub-category + assets + magnitude (when known).
- `lib/event_impact/impact_modeler.py` (~500 LOC) — pure: takes the corpus + OHLCV history, computes reaction windows (1h, 6h, 24h, 7d) per asset per event, returns an `ImpactProfile` per `(category, sub-category)` with: `mean_return_pct`, `median_return_pct`, `n`, `stdev`, `confidence_interval_95`, `direction_consensus` ∈ [-1, +1].
- `lib/event_impact/lookup.py` (~250 LOC) — pure: `lookup(event: MacroEvent, asset: str, horizon_hours: int) -> ExpectedReaction` returns the fitted profile. Handles category fallback (specific → general) and "we have no data, return wide band" cases honestly.
- `services/event_impact/build.py` (~200 LOC) — one-shot script: fetches OHLCV, builds the model, writes `data/event_impact/model_<date>.json` with provenance.
- `plugins/claw-sapphire/tools/internal/event_impact.py` (~300 LOC) — stdin-JSON. Actions: `lookup`, `corpus`, `rebuild`, `accuracy-audit` (compares model predictions to actual outcomes for events after the model was last built).
- `plugins/claw-sapphire/tools/event_impact.py` — shim.
- `tests/unit/test_event_corpus.py` (≥ 14 cases): every category present, every event has required fields, dedup logic.
- `tests/unit/test_impact_modeler.py` (≥ 22 cases): synthetic event + synthetic OHLCV → expected reaction; window correctness; small-sample wide-band; survivorship-bias filter (don't include exchanges that ceased operating without explicit annotation).
- `tests/unit/test_event_impact_lookup.py` (≥ 14 cases): cache, fallback, "no data" handling.
- `plugins/claw-sapphire/tests/test_event_impact.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `event_impact`.
- `docs/products/event-impact-modeling-0.1.0.md` (1500+ words) — with worked examples (FOMC rate hike → expected BTC reaction).
- `docs/ops/event-impact-runbook.md` (1200+ words).
- `data/event_corpus/events.jsonl` — initial committed corpus of ≥ 80 historical events with citations in metadata.

**Constraints**:
- **No live calls in build script tests.** OHLCV fetched via the existing OpenBB local API at `:6900` (mock in tests).
- **Honesty about overfitting**: with ≤ 20 FOMC observations, "expected reaction" is wide. Reflect this in the confidence interval and document the methodology.
- **Survivorship-bias awareness**: be explicit about which events the corpus excludes (e.g., exchanges that delisted before reaching reasonable volume).

**PR title**: `feat(intel): historical event-impact modeling 0.1.0`

---

### LANE 8 — Counter-Party Intelligence on Hyperliquid (Top Trader Tracking)

**Why it matters**: Hyperliquid is one of the few perp DEXs where top-trader positions are PUBLIC. Smart-money tracking is an established alpha source (e.g., Whale Alert, Nansen Smart Money). Tranche 2 shipped the public-feed subscription; this lane extends it with **counter-party intelligence**: track the top-N traders by 30d PnL, watch their position changes, emit `counterparty.smart_money.move` events when they significantly add or trim positions. The correlation engine consumes these as a high-weight signal.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-counterparty-intel` on `feat/counterparty-intelligence`.

**Templates to read first**:
- `services/hyperliquid/src/hyperliquid_bot/public_feed.py` — existing public-feed subscriber.
- `lib/correlator/sources.py` — how to plug new source into correlator.

**Files**:
- `lib/counterparty/__init__.py`
- `lib/counterparty/tracker.py` (~500 LOC) — pure: takes Hyperliquid public-trader API responses, ranks traders by 30d / 90d realized PnL + Sharpe, maintains a watchlist of top-N traders (default N=50), tracks each watchlisted trader's open positions over time. Emits `position.changed` records when a trader's position shifts > X%.
- `lib/counterparty/sources.py` (~300 LOC) — Hyperliquid API client extension to query trader leaderboards + per-trader positions. Live behind `SAPPHIRE_HYPERLIQUID_LIVE=1` (same env flag as Tranche 2's feed).
- `lib/counterparty/signal_generator.py` (~250 LOC) — converts position changes into `CounterpartySignal` records suitable for the correlator: `{asset, side, magnitude, traders_corroborating: int, smart_money_consensus: float}`.
- `services/counterparty/run.py` (~250 LOC) — daemon: every 5 minutes refresh leaderboard + positions, emit signals. Shares the Hyperliquid live env flag with Tranche 2's feed daemon.
- `plugins/claw-sapphire/tools/internal/counterparty_intel.py` (~350 LOC) — stdin-JSON. Actions: `leaderboard`, `position-changes`, `smart-money-consensus`, `status`.
- `plugins/claw-sapphire/tools/counterparty_intel.py` — shim.
- `tests/unit/test_counterparty_tracker.py` (≥ 18 cases).
- `tests/unit/test_counterparty_sources.py` (≥ 12 cases): all HTTP mocked.
- `tests/unit/test_counterparty_signal_generator.py` (≥ 14 cases).
- `plugins/claw-sapphire/tests/test_counterparty_intel.py` (≥ 10 cases).
- `infra/tool-registry.yaml` — append `counterparty_intel`.
- `docs/products/counterparty-intel-0.1.0.md` (1200+ words).
- `docs/ops/counterparty-intel-runbook.md` (1200+ words).

**Caps**:
- `MAX_TRADERS_TRACKED = 100`
- `MAX_REFRESH_PER_HOUR = 12`
- `MIN_TRADER_30D_PNL_USD = 50_000` (skip noisy small accounts)
- `POSITION_CHANGE_SIGNAL_THRESHOLD_PCT = 15`

**Constraints**:
- **Public-data only.** No attempts to deanonymize wallet addresses beyond what Hyperliquid's public leaderboard already exposes.
- **Read-only.** This MUST NOT initiate any trades.
- **No wallet keys touched.**
- **Operator opt-in for live data** via the same `SAPPHIRE_HYPERLIQUID_LIVE=1` flag.

**PR title**: `feat(signals): hyperliquid counter-party intelligence 0.1.0`

---

## 4. Cross-lane integration (mandatory after lane completion)

After all 8 lanes have merged independently, run **one synthesis PR** that wires them together:

**Branch**: `feat/intelligence-integration-pass`

**Wiring**:
1. **Narrative Synthesis (Lane 1) reads from Cross-Asset (Lane 2)**: the narrative engine's prompts include the current regime label.
2. **Narrative Synthesis (Lane 1) reads from Macro Intel (Lane 3)**: narratives include "next scheduled macro event in window: …" context.
3. **Narrative Synthesis (Lane 1) reads from On-Chain (Lane 6)**: narratives include the on-chain regime tag.
4. **Narrative Synthesis (Lane 1) reads from Counter-Party (Lane 8)**: narratives include "smart money consensus: 4 of top-50 traders increased BTC long in last 24h."
5. **Adversarial Defense (Lane 5)** subscribes to ALL the new event topics from Lanes 1, 2, 3, 6, 7, 8 and emits telemetry.
6. **Event-Impact (Lane 7) integrates with Macro Intel (Lane 3)**: when macro daemon emits a `macro.event.detected`, Event-Impact looks up the expected reaction and emits `event.expected_reaction.published`. Narrative engine consumes this.
7. **Cross-Asset (Lane 2) feeds correlator**: regime label becomes a new source weight in the correlator (high-weight when regime is `crisis_correlation_spike`, low-weight when `regime_uncertain`).
8. **Observability dashboard (from Tranche 3)**: extend with cards for each new feed's rate + last-event time. Read-only extension.
9. **Acquirer microsite (from Tranche 3)**: extend the Capabilities section with the 8 new surfaces.

**This integration PR adds NO new business logic**; it only wires existing surfaces together. Verification: every wiring is exercised by an integration test that runs against fully mocked Lane outputs.

**PR title**: `feat(intelligence): tranche-4 integration pass`

---

## 5. Verification protocol (every lane)

Before opening a PR, get all six green from inside the worktree:

```bash
ruff check .
/usr/local/bin/python3 -m pytest <NEW_TEST_FILES> -q --tb=short
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

`0 FAIL` mandatory. Run the two pytest blocks SEPARATELY (the conftest collision is documented).

---

## 6. PR template

Each PR body MUST include:
- **What this enables** — acquisition framing.
- **Cross-lane integration** — how this lane plugs into Tranche 4's other lanes.
- **Safety posture** — env gates, caps, no-secrets-at-rest.
- **Local verification** — six command outputs.
- **Files changed** — file list.
- **Follow-ups not in this PR** — be honest.

For research lanes (Lane 4 + research-half of Lane 5):
- **Sources cited** — list of primary URLs with retrieval dates.
- **Word count** — confirmed.
- **Provenance envelope** — confirm sidecar exists.

---

## 7. Merge protocol (UPDATED)

Use the safe-merge wrapper (Tranche 3 Lane 6 should have shipped it):
```bash
~/Code/Sapphire/scripts/ops/sapphire_safe_merge.sh <PR>
```

If that script is missing for any reason, fall back to:
```bash
TITLE=$(gh pr view <N> --json title --jq '.title')
SUBJECT="${TITLE} [skip ci]"
gh -R arigatoexpress/Sapphire pr merge <N> --squash --admin --delete-branch -t "$SUBJECT"
gh run list --limit 5 --json databaseId,status --jq '.[] | select(.status=="queued" or .status=="in_progress") | .databaseId'
```

---

## 8. Closeout deliverable

After all 9 PRs (8 lanes + 1 integration pass) merge, write `docs/handoffs/codex-megaprompt-tranche-4-2026-04-29-report.md` with:

1. **Final main SHA** + open PR/issue counts.
2. **Per-lane status table** — including key cross-lane integrations exercised.
3. **Verification at handoff** — six commands' tail.
4. **Operator-owed actions** — Glassnode key, Santiment key, ETH/SOL RPC URLs, Gemini live narrative key, etc.
5. **Skipped lanes (if any)** with one paragraph each.
6. **Tranche 5 backlog** — what's the next tranche about? (Suggestion: live-soak windows, real Telegram channel curation results, dashboards-as-public-product, paper-to-live ramp execution at $50.)
7. **Squash-merge subject audit** — every subject ended with `[skip ci]`.
8. **NEW: Integration-pass evidence** — confirmation that the 9 wirings in §4 are all exercised by tests.

Then update `~/.claude/projects/-Users-aribs/memory/MEMORY.md` with one line pointing to a new `project_2026-04-29_codex_tranche_4.md`.

---

## 9. Posture reminders for deep work

- **Quality over quantity.** A polished single deliverable per lane beats three shallow ones. If a lane needs more time, take it; skip a lower-priority lane instead.
- **Cite primary sources** in research lanes. "According to a 2025 blog post on palantir.com/blog/ontology" is acceptable; "Palantir says X" without a citation is not.
- **Bounded LLM use** in build lanes. Mirror gemini_ooda's safety story precisely; never reach for more than the lane's authorized cap.
- **Provenance envelopes everywhere**. Every artifact gets a sibling `.envelope.json`.
- **Honesty over hype**. If a lane discovers something the operator should know (e.g., a Glassnode metric whose API changed and breaks our assumption), say so plainly.
- **Trading critical path is sacred**. Do not modify it.
- **Cross-lane awareness**. Even if your sub-agent is dispatched to a single lane, read the other lanes' specs so wiring boundaries are clear.
- **The integration-pass PR is non-optional**. The compound edge only exists if the wirings happen.

This tranche is the one where Sapphire's claim of being a multi-modal intelligence system becomes provable in code, in docs, and in narrative. Spend the time.

Now go.
