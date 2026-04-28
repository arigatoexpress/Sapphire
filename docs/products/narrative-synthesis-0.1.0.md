# Narrative Synthesis 0.1.0

Narrative Synthesis 0.1.0 turns Sapphire's correlated market signal output into a structured research thesis that an operator can read, audit, and challenge. The Tranche 3 signal correlator already fuses multiple feeds into a deterministic `edge_score`, `consensus`, `corroborated_by`, and `divergent_sources` payload. That is the right machine-readable foundation, but it is not yet a human-facing intelligence product. A score tells Ari that something moved. A narrative thesis explains why the move matters, what evidence supports it, what would invalidate it, and what to watch next.

This product is designed for Sapphire's production-autonomy posture: dry-run by default, bounded live inference only when explicitly enabled, provenance on every artifact, and a deterministic rubric before publication. It does not place trades, size positions, send Telegram messages, or mutate upstream signal sources. The output is research intelligence that can feed dashboards, daily briefs, notebooks, and future human-review workflows.

## What It Produces

The engine emits a `NarrativeThesis` object for one correlated signal. The core fields are:

- `thesis_one_paragraph`: a concise explanation of why the edge exists.
- `evidence_bullets`: source-tied facts from the correlated signal.
- `counter_thesis_one_paragraph`: the strongest plausible contrary read.
- `invalidators`: concrete observations that would weaken or cancel the thesis.
- `next_signal_to_watch`: the single next observable item the system should monitor.
- `implied_position`: one of `long_strong`, `long_mild`, `neutral`, `short_mild`, `short_strong`, or `no_position`.
- `confidence`: a bounded 0.0 to 1.0 confidence value derived from the signal and/or live model output.
- `caveat_block`: an explicit research-only safety caveat.
- `provenance_envelope`: generator, version, prompt version, caps, source signal hash, source provenance, and mode.

The implied position is not an order and is not a trade execution instruction. It is a compact thesis label. The mapping is intentionally simple and auditable: strong positive edges map to `long_strong`, mild positive edges to `long_mild`, flat edges to `neutral`, mild negative edges to `short_mild`, strong negative edges to `short_strong`, and insufficient data to `no_position`.

## Why This Matters

Sapphire now has multiple intelligence layers: TradingView signals, Hyperliquid public-feed signals, Kronos or TA forecasts, Telegram-derived channel intelligence, threat context, convergence watchlists, and sovereign thesis data. The correlator makes these sources comparable. Narrative Synthesis makes them legible.

The practical user value is speed and judgment:

1. It reduces operator load. Ari can scan one thesis rather than mentally combine raw source rows.
2. It exposes disagreement. Divergent sources are not hidden; they become part of the counter-thesis.
3. It improves auditability. Every thesis carries a source hash and provenance envelope.
4. It creates a repeatable research product. The same signal produces the same dry-run thesis, which makes tests and regression reviews meaningful.
5. It provides a publication gate. The rubric blocks weak structure, low evidence density, inconsistent direction, or missing caveats before a daemon writes a thesis artifact.

## Safety Model

Dry-run is the default path. In dry-run mode the engine never reads a Gemini key and never contacts Google. It deterministically builds a thesis from the `CorrelatedSignal` fields. This keeps CI, local operator runs, and daemon ticks safe.

Live mode is available only when all gates pass:

- the caller requests `mode=live`;
- `SAPPHIRE_NARRATIVE_LIVE=1` is set;
- a Gemini key is present in `~/.sapphire/secrets.env` or process env;
- the prompt passes the Sapphire sensitivity classifier;
- the live-call rate limit allows the request;
- the monthly token cap allows the projected spend;
- the model response parses into the expected JSON schema.

If any gate fails, the engine falls back to a deterministic dry-run thesis with a mode reason such as `dry-run-blocked-by-env`, `dry-run-no-key`, `dry-run-safety`, `dry-run-rate-limited`, `dry-run-live-error`, or `dry-run-live-unparseable`. Secrets are never returned or logged. The caps for 0.1.0 are:

- max output tokens: 6144;
- max input chars: 18000;
- max live calls per hour: 6;
- max live tokens per month: 750000;
- publish rubric threshold: 0.70.

## Rubric

The rubric is deterministic and local. It does not call an LLM judge. It scores five dimensions in `[0, 1]`:

- `structural_validity`: required fields exist, evidence and invalidators have enough substance, confidence is bounded, and the implied position is valid.
- `actionability`: invalidators are concrete, the next signal to watch is specific, and the caveat keeps the result in research context.
- `citation_density`: evidence includes source names, consensus labels, and numeric facts.
- `internal_consistency`: the implied position matches the correlated edge and insufficient data maps to `no_position`.
- `hedging_appropriateness`: the thesis includes a real counter-case, invalidators, and research-only caveats.

The overall score is the average of the five dimensions. The daemon only publishes rows whose overall score is at least 0.70. A low score does not crash the system; it becomes a dropped row in the daemon result.

## Worked BTC Example

Example correlated signal:

```json
{
  "symbol": "BTC",
  "timeframe": "1h",
  "edge_score": 0.72,
  "consensus": "AGREE_BULL",
  "corroborated_by": ["tradingview", "kronos_forecast", "hyperliquid"],
  "divergent_sources": [],
  "bull_sources": ["tradingview", "kronos_forecast", "hyperliquid"],
  "bear_sources": [],
  "neutral_sources": ["threat_intel"],
  "freshness_seconds": 90,
  "contributing": 4,
  "raw_score": 0.648,
  "agreement_multiplier": 1.2,
  "contradict_factor": 1.0,
  "total_weight": 3.4,
  "generated_at": "2026-04-28T11:59:00+00:00"
}
```

Dry-run thesis:

```json
{
  "symbol": "BTC",
  "timeframe": "1h",
  "implied_position": "long_strong",
  "confidence": 0.7944,
  "thesis_one_paragraph": "BTC 1h carries a strong bullish research thesis because the correlated edge_score is +0.720 with consensus AGREE_BULL across 4 fresh sources. The strongest explanation is the source cluster around tradingview, kronos_forecast, hyperliquid; freshness is 90s, so the read is recent enough for monitoring but not a live execution instruction. The implied posture is long strong until a new correlated signal changes the edge by at least 0.10 or a named invalidator trips.",
  "evidence_bullets": [
    "edge_score +0.720 and raw_score +0.648 map to implied_position=long_strong.",
    "consensus=AGREE_BULL; corroborated_by=['tradingview', 'kronos_forecast', 'hyperliquid']; divergent_sources=[].",
    "bull_sources=['tradingview', 'kronos_forecast', 'hyperliquid']; bear_sources=[]; neutral_sources=['threat_intel'].",
    "agreement_multiplier=1.200, contradict_factor=1.000, total_weight=3.400.",
    "freshness_seconds=90; source_signal_generated_at=2026-04-28T11:59:00+00:00."
  ],
  "counter_thesis_one_paragraph": "The counter-thesis is that no named divergent source may be early, stale, or observing a different timeframe than the dominant cluster. If liquidity or macro context shifts before the next correlator tick, the numeric edge could compress without warning.",
  "invalidators": [
    "Monitor whether the next correlator tick moves edge_score by more than 0.10 against the thesis.",
    "Watch for divergent_sources expanding to two or more independently weighted feeds.",
    "Compare freshness_seconds; invalidate if the dominant source cluster ages beyond the 24h hard limit.",
    "Confirm whether agreement_multiplier falls below 1.00 or contradict_factor tightens materially."
  ],
  "next_signal_to_watch": "Watch the next BTC 1h signal.correlated row for an edge_score delta greater than 0.10 plus any new divergent_sources.",
  "caveat_block": "Research-only dry-run narrative. This thesis does not place trades, size positions, send Telegram messages, or override Sapphire's paper-only safety posture."
}
```

This is intentionally more like a desk note than a trading signal. It says what the system sees, what would change the conclusion, and how to monitor the next step. The operator can quickly answer: Is the thesis directional? Yes, strong bullish. Is the source agreement broad? Yes, three named bull sources and one neutral source. Is there an invalidation rule? Yes, edge change greater than 0.10, more divergent feeds, stale data, or reduced agreement. Is there an action? Watch the next correlated row. Is it live trading? No.

## Interfaces

Library:

```python
from lib.synthesis import synthesize

result = synthesize(correlated_signal_dict)
```

Service:

```bash
python3 services/synthesis/run.py run-once
python3 services/synthesis/run.py daemon --mode dry-run --poll-interval-seconds 1800
python3 services/synthesis/run.py status
```

Plugin:

```bash
echo '{"action":"synthesize-once","signal":{"symbol":"BTC","timeframe":"1h","edge_score":0.72,"consensus":"AGREE_BULL","contributing":4}}' \
  | python3 plugins/claw-sapphire/tools/narrative_synthesis.py
```

Plugin actions are `synthesize-once`, `latest`, `history`, `rubric-score`, and `status`.

## 0.1.0 Scope

This release is the bounded foundation. It does not add dashboard UI, does not alter the Tranche 3 correlator, and does not change trading execution. It creates the synthesis layer, tests it, documents it, registers the plugin tool, and ships a LaunchAgent template that remains dry-run by default. Later releases can add dashboard panels, richer source adapters, human approval UX, and cross-asset narrative aggregation.

## Product Adoption Path

The first adoption path is operator-assisted research. Ari or a local agent can run `narrative_synthesis.py` against a single inline signal and read the resulting thesis in the terminal. This is the right mode when validating a new feed, checking a suspicious edge, or preparing a daily note. It has the smallest blast radius because the input is explicit and no daemon state is involved.

The second adoption path is the scheduled daemon in dry-run mode. Once the correlator is producing regular JSONL rows, the synthesis service can watch for edge changes and append publishable theses. The 0.10 edge-delta rule intentionally avoids rewriting a narrative for every tiny score movement. In practice, this means the output queue should represent meaningful narrative changes rather than noise. If BTC moves from +0.71 to +0.74, the old thesis remains valid. If BTC moves from +0.71 to +0.48, or from +0.18 to -0.05, the service has a reason to write a new note.

The third adoption path is downstream consumption. A dashboard can read `data/narratives/<date>/theses.jsonl` and show the latest thesis per symbol. A daily brief can include only rows whose rubric score is comfortably above the threshold. A future human-review layer can ask the operator to approve, reject, or annotate the thesis before it is promoted into a formal morning note. All of these are read-only consumers of the narrative artifact.

Live Gemini mode is a later-stage enhancement, not a prerequisite for adoption. The deterministic dry-run output is already structured enough to provide a useful explanation and to exercise all service plumbing. Live mode should be reserved for cases where the dry-run template is too rigid and a model can add genuinely better synthesis while staying inside the same JSON schema and rubric.

## Known Limits

Narrative Synthesis 0.1.0 is intentionally conservative. It does not fetch missing evidence. If the correlator row omits a source, the thesis cannot cite that source. It does not know whether an exchange outage, macro release, or governance event happened unless that context is already present in the correlated signal. It does not compare a new thesis against a long historical narrative chain. It does not decide whether a thesis should become a trade. These are features for future layers.

The rubric is also heuristic. It rewards source names, numbers, concrete invalidators, and directional consistency. That is useful for preventing empty prose, but it is not a guarantee that the market read is correct. A beautifully structured thesis can still be wrong if the upstream sources are stale, biased, or incomplete. Conversely, a terse but correct operator note might score lower if it does not include enough structured evidence. The rubric is therefore a publication gate, not an oracle.

The `confidence` field is bounded but not calibrated to realized returns. In dry-run mode it is derived from edge magnitude, source count, contradiction, and no-position status. It should be read as thesis confidence, not expected PnL, probability of profit, or statistical forecast accuracy. Calibration can come later once narrative outputs are compared against subsequent signal evolution and paper-trading outcomes.

## Buyer-Facing Summary

For a buyer or stakeholder, the story is simple: Sapphire now explains its own signals. Instead of handing an operator a black-box score, it produces a short research memo with evidence, disagreement, invalidation criteria, and a next thing to watch. It is safer than a free-form chatbot because the input is bounded, the schema is fixed, secrets are redacted, live model use is gated, and every output is scored before publication. It is more useful than a plain rule engine because it packages the rule outcome into language that humans can inspect quickly.

That combination is the product value. Sapphire becomes not only a signal factory, but an intelligence desk that can say, "Here is the edge, here is why it exists, here is why it might be wrong, and here is the next observation that matters." For production autonomy, that is the difference between automation that merely acts and automation that leaves an auditable trail of judgment.
