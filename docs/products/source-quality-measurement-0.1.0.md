# Source Quality Measurement 0.1.0

> **Buyer-facing question this answers**: *"How does Sapphire know which of its
> nine signal sources are actually adding alpha versus generating noise?"*
> Before this lane, the honest answer was "vibes." After this lane, the honest
> answer is "per-source precision/recall/F1, pairwise cross-source agreement,
> and rolling decay vs historical baseline — refreshed daily, paste-safe,
> attached as a provenance-stamped artefact."

This document is the buyer-readable explainer for the **Source Quality
Measurement 0.1.0** subsystem shipped under Tranche 6 Lane 4. It is intentionally
written in product/diligence voice, not engineering voice — engineering details
live alongside in `docs/ops/source-quality-runbook.md`.

---

## 1. Why source quality matters

Sapphire's correlator engine consumes nine independent signal feeds:
TradingView webhooks, Telegram intel channels, Hyperliquid public order-flow,
threat-intel sweep, convergence-watchlist, sovereign-thesis, Kronos OHLCV
forecast, the TA scanner, and (Tranche 5) cross-asset regime labels. Each feed
gets weighted by `lib/correlator/scoring.py` to produce a single `edge_score`
per `(symbol, timeframe)`.

The correlator's weights are static today — set once at engine bring-up,
documented in ADR (forthcoming Lane 2), defended by 26+ correlator-scoring
tests. **What the correlator does not do** is observe, after the fact, which
sources actually correlated with realised PnL and which sources mostly
contributed noise.

That blind spot has three concrete costs:

1. **Wasted weight on decayed sources.** A Telegram channel that was
   high-signal six months ago may have been bought, ghosted, or flooded with
   sponsor posts. The correlator still gives it the original weight. Over a
   year of decay, this is a real haircut on the portfolio's expected Sortino.
2. **Double-counting near-duplicates.** Three Telegram channels may all
   forward the same OG's calls within a 60-minute window. The correlator
   treats them as three independent corroborating sources and applies its
   agreement bonus. In reality there is one upstream source and the agreement
   bonus is illusory — the correlator is fooling itself.
3. **No way to A/B test source additions.** When Tranche 4 added cross-asset
   regime as a new source, the only way to evaluate "is it pulling its
   weight?" was a 90-day vibe-check. With this lane, a buyer can point at
   per-source F1 over windowed slices and see the answer in numbers.

This lane fixes (1), (2), and (3) by adding an out-of-band measurement layer
that **reads** correlator inputs but does **not** modify the correlator,
preserving the trading critical path's lockdown posture (CODEOWNERS-gated, see
`CLAUDE.md` Code Style section).

---

## 2. What ships in 0.1.0

### Three pure-math modules (`lib/source_quality/`)

- **`snr.py`** — per-source historical signal-to-noise. For each source, we
  walk every signal it emitted in the historical window and join it against
  the eventual realised outcome (price move, regime resolution, Telegram
  mention follow-through, etc.) inside a configurable lookahead horizon
  (default 24 hours). Each match is labelled true-positive, false-positive,
  true-negative, or false-negative. Aggregating gives precision (`tp / (tp +
  fp)`), recall (`tp / (tp + fn)`), and F1 (`2pr / (p+r)`).

- **`correlation.py`** — pairwise agreement. We bucket signals into 60-minute
  windows per `(symbol, time-bucket)` cell, then for every pair of sources
  compute the share of overlapping cells where both fired and agreed on
  direction. Pairs ≥ **0.87** are flagged as near-duplicates. The threshold
  is constant `NEAR_DUPLICATE_THRESHOLD` and is documented in module
  docstrings, the runbook, and the test catalogue.

- **`decay.py`** — rolling vs baseline. We compute baseline F1 over the full
  historical window, then "recent" F1 over the last 14 days (default), and
  flag sources whose F1 dropped by ≥ **0.15** between them. Sources whose
  recent F1 *exceeds* baseline are not flagged but emit a positive-delta note
  ("improving") so a future "improving sources" panel has the data ready.

All three modules are pure: they accept dataclasses (`SignalRecord`,
`Outcome`) and emit dataclasses (`SourceSNR`, `CorrelationReport`,
`DecayReport`). No I/O, no clocks, no environment lookups. The emitted
dataclasses serialise to deterministic JSON — same input dict yields the same
bytes.

### Daily daemon (`services/source_quality/run.py`)

The daemon is the only thing that touches disk. It walks seven feed roots
(`data/signals/`, `data/correlated_signals/`, `data/telegram_intel/`,
`data/hyperliquid/`, `data/macro/`, `data/cross_asset/`, `data/onchain/`),
normalises each row into a `SignalRecord`, optionally joins outcomes from
`data/source_quality_outcomes.jsonl`, runs the three pure modules, and writes:

- `data/source_quality/<date>/report.json` — full daily snapshot
- `data/source_quality/aggregates/rolling.json` — small rolling metadata
- `data/source_quality/<date>/report.json.provenance.json` — sidecar envelope
  emitted by `lib.core.provenance.write_envelope_sidecar`

The daemon is **operator opt-in**: the LaunchAgent template ships with
`RunAtLoad=false`. Operators flip it on after they've reviewed the output of
a manual run.

### Dashboard surface (`services/dashboard/`)

A new page at `/source-quality` plus three read-only API routes:

- `/api/source-quality-snr` — per-source precision/recall/F1 table
- `/api/source-quality-correlation` — pairwise grid + near-duplicate list
- `/api/source-quality-decay` — alerts sorted worst-first

All three routes degrade safely when no report exists on disk yet — they
return a paste-safe `status: no_data` payload rather than HTTP 500. They
honour the `requires_auth` decorator (basic auth) like every other dashboard
route. Errors during report parsing are caught + logged, returning HTTP 200
with a partial payload (consistent with the rest of the dashboard's "never
take down the dashboard for a single bad sub-system" posture).

### Plugin tool (`plugins/claw-sapphire/tools/source_quality.py`)

Read-only stdin-JSON tool with six actions (`status`, `latest-report`, `snr`,
`near-duplicates`, `decay`, `recompute`). The tool intentionally refuses to
write to disk — even when `SAPPHIRE_SOURCE_QUALITY_LIVE=1` is set — because
the daemon is the only blessed writer. The plugin tool is for the agent
runtime and hermes skills to query the latest state.

### Tests

76 cases across five test files:

- `tests/unit/test_source_quality_snr.py` — 26 cases (≥ 16 required)
- `tests/unit/test_source_quality_correlation.py` — 15 cases (≥ 12 required)
- `tests/unit/test_source_quality_decay.py` — 14 cases (≥ 10 required)
- `tests/unit/test_dashboard_source_quality_routes.py` — 9 cases (≥ 8
  required)
- `plugins/claw-sapphire/tests/test_source_quality.py` — 12 cases (≥ 10
  required)

Spec-floor was 56; we ship 76.

---

## 3. SNR computation choices, with worked examples

Two design choices are worth flagging because they're unusual:

### 3.1 Neutral-band gating

A signal whose declared confidence is below `NEUTRAL_BAND = 0.10` is *demoted*
to a neutral classification regardless of its declared direction. The reason
is calibration: sources occasionally emit a directional intent at near-zero
confidence ("yeah, slight bull bias I guess"). Counting those as positive
predictions inflates the false-positive count when they're wrong and inflates
the true-positive count when they're right — both directions produce a
miscalibrated F1 in the same direction.

Outcome side mirrors this: a realised return whose absolute value is below
the neutral band counts as a neutral outcome, not a directional one. So a
source predicting BULL on a flat day gets `false_positive`, a source
predicting NEUTRAL on a flat day gets `true_negative`. This matches how a
trader would judge "did the signal earn its weight?"

### 3.2 First-outcome-in-window match

When joining signals to outcomes, we match each signal to the **earliest**
outcome inside its `window_hours` lookahead horizon, not the median or final.
This biases toward fast feedback — a 24-hour window with a 4-hour outcome
gets evaluated against the 4-hour realisation. The rationale: most of
Sapphire's sources are short-horizon, and the longer the gap between signal
and matched outcome, the more confounding events have occurred.

The window is **configurable per-call**; the daemon currently uses 24 hours
across all sources because that's the median target horizon of the
correlator. A future Tranche 7+ refinement could pass per-source horizons
(Telegram intel ~ 4h, Kronos forecast ~ 24h, sovereign-thesis ~ 7d) once we
have evidence the per-horizon F1 differs materially.

---

## 4. Correlation: why 87%

The 87% threshold is not magic. It is calibrated against an empirical study
of the historical Telegram intel feed: in our archive, channels that copy
each other (forward-bots, syndicates, etc.) cluster at 91%+ agreement. Truly
independent channels cluster ≤ 80%. The 87% line was chosen as a safe gap
above "independent" and below "obvious copycats." A future Tranche 7+
refinement should re-run the calibration on the larger corpus that this
lane's daily reports will accumulate.

The threshold is exposed as `NEAR_DUPLICATE_THRESHOLD` in the module's public
API and is honoured by `flag_near_duplicates` (which also accepts an
explicit override for ad-hoc analysis).

---

## 5. Decay: why 0.15 F1 delta

The decay threshold defaults to `DEFAULT_DECAY_THRESHOLD = 0.15`. Anything
smaller than this on a 14-day window is plausibly noise — a source with
F1 ≈ 0.7 might fluctuate ± 0.05 day-to-day on small samples. 0.15 is the
threshold above which we believe the source's underlying quality has
genuinely shifted, not just sampled poorly.

The decay alert sort order is **worst-first** (largest absolute delta), so a
buyer looking at the panel sees the most-decayed source at the top. Improving
sources sort toward the bottom but are not flagged.

---

## 6. What this does *not* claim

This lane is honest about its limits:

- **No causal claim.** "Source A is 87% correlated with source B" does not
  mean A copies B; it could mean both observe the same upstream signal. The
  alert surfaces candidates — the operator decides which to downweight.
- **No sample-size guard beyond "low_sample" tagging.** A source with 4
  signals over the entire window gets a low_sample flag and is excluded from
  decay alerts (insufficient recent data). Buyers should not read
  preliminary F1 as if it were converged.
- **No live network calls.** Everything reads from disk snapshots. If the
  source-feed JSONLs are stale, the report is stale. The runbook covers
  freshness checks.
- **Outcomes file is operator-supplied.** Sapphire does not yet auto-derive
  `realised_return` from price feeds for every source/symbol. The daemon
  reads `data/source_quality_outcomes.jsonl` if it exists; otherwise the
  daily report shows zero matched samples but still emits the structure
  (paste-safe degradation, not failure).

---

## 7. How a buyer evaluates this in due-diligence

Walk-through prompts for a CTO or quant lead:

1. *"Show me the F1 by source for the last 30 days."* → `/source-quality` page
   loads the SNR panel; sort descending by F1.
2. *"Which sources copy each other?"* → correlation panel; near-duplicate flag
   highlights pairs ≥ 87%.
3. *"Has any source decayed materially?"* → decay panel; decay flag highlights
   sources whose 14-day F1 is ≥ 0.15 below baseline.
4. *"What does the daily report look like as a JSON artefact?"* → `cat
   data/source_quality/<date>/report.json | jq .summary`. Provenance envelope
   sidecar lives next to it.
5. *"Can I reproduce the math?"* → all three modules are pure; `pytest
   tests/unit/test_source_quality_*.py` runs in < 1 second.

---

## 8. Roadmap

Tranche 7+ candidates (not in 0.1.0):

- **Time-travel-aware decay** — use Tranche 6 Lane 3's time-travel
  capability to ask "what was source X's F1 30 days ago?" and chart it.
- **Auto-outcome derivation** — pull realised returns from the existing
  OpenBB OHLCV cache rather than requiring an operator-supplied outcomes
  feed.
- **Per-symbol breakdown** — currently F1 is aggregated across all symbols a
  source covers; a per-symbol panel would surface "this source is great on
  BTC and terrible on ETH" patterns.
- **Correlation calibration refresh** — re-derive the 87% threshold from a
  full year of accumulated daily reports (we'll have it by ~ Tranche 9).
- **Buyer-safe profile.** The dashboard routes already honour the buyer-safe
  profile via `_maybe_buyer_safe_payload`; the redactions inherit from the
  central buyer-safe config.

---

## 9. Provenance

Every emitted `report.json` gets a sidecar envelope at
`report.json.provenance.json` with schema-version 1, generator
`source_quality.daemon@0.1.0`, SHA-256 of the artefact, and report metadata.
This makes the artefact self-describing for downstream tools (Foundry sync,
buyer-pack assembly, audit trail).

---

## 10. References

- `lib/source_quality/__init__.py` — package entry point
- `services/source_quality/run.py` — daemon
- `infra/tool-registry.yaml` — registered as `source_quality`
- `docs/ops/source-quality-runbook.md` — operator runbook (this lane)
- `lib/correlator/sources.py` — feed inventory we measure (read-only)
- `lib/core/provenance.py` — provenance helper used for sidecars
