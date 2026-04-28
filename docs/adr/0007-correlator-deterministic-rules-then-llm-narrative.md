# ADR 0007 — Correlator: deterministic rules first, LLM narrative second

- **Status**: accepted
- **Date**: 2026-04-29
- **Authors**: Sapphire ops
- **Related**: ADR 0004, ADR 0005

## Context

Sapphire's correlator (`lib/correlator/`) and narrative engine
(`lib/synthesis/`) together answer the question "what's the system
saying about asset X right now?" Two approaches existed at the start of
Tranche 3:

1. **End-to-end LLM pipeline**: every signal goes into a prompt; the
   LLM emits the correlated view, scoring, and narrative in one pass.
   Fast to ship; expensive to verify; non-deterministic; hard to test.
2. **Deterministic rules**: hand-written scoring rules over signal
   sources. Cheap to verify; impossible to author at the speed of new
   sources; brittle against edge cases.

Either alone is a dead end. End-to-end LLM cannot pass diligence —
"how do you know it's not hallucinating?" has no good answer. Pure
rules cannot produce the human-readable narrative buyers expect.

## Decision

Sapphire splits the pipeline into two layers:

1. **Deterministic rules layer** (`lib/correlator/`):
   - `lib/correlator/sources.py` — adapter pattern, one class per
     source (Telegram, Twitter, RSS, threat intel, on-chain, SEC,
     macro, etc).
   - `lib/correlator/scoring.py` — pure functions: `edge_score`,
     `agreement_bonus`, `freshness_decay`. Bounded outputs in
     `[-1, +1]`. Property-tested (Lane 1 of Tranche 6).
   - `lib/correlator/engine.py` — orchestrator: pulls from sources,
     computes edge scores, returns a `CorrelatedView` dataclass.
   - **No LLM calls in this layer.** Deterministic given inputs.
2. **LLM narrative layer** (`lib/synthesis/`):
   - `lib/synthesis/narrative_engine.py` — takes a `CorrelatedView`
     produced by the deterministic layer, optionally invokes an LLM
     to produce a human-readable narrative. Mock-default per ADR 0004.
   - `lib/synthesis/rubric.py` — scoring rubric for narrative quality.
   - The LLM never sees raw signals; it sees the typed output of the
     deterministic layer. This means the LLM is reasoning over a
     bounded structured surface, not free-form data.

**Provenance flows both layers**: the narrative envelope cites the
correlator envelope; the correlator envelope cites the source data
sha256s. Buyer can chase the chain back to inputs.

## Consequences

- **Positive**:
  - Deterministic answer to "show me what the correlator said and why"
    — `engine.py` returns a typed object with per-source scores.
  - Narrative quality is bounded by what the deterministic layer
    surfaces; the LLM cannot invent signals not in the typed input.
  - Property tests on `scoring.py` give buyer-grade rigor (Lane 1 of
    Tranche 6: `test_correlator_scoring_properties.py` — edge_score
    bounded, agreement_bonus monotone, freshness decay bounded
    below).
  - LLM costs are gated by `SAPPHIRE_NARRATIVE_LIVE` (ADR 0004); the
    deterministic layer always runs.
- **Negative**:
  - Two-layer code is more code. Adding a new source means adapter
    + scoring tweak + (sometimes) narrative-prompt update.
  - The deterministic layer's scoring weights are hand-tuned, not
    learned. We may leave alpha on the table relative to a fully
    learned scorer; offset by ADR 0009 (source quality measurement
    in Tranche 6 Lane 4) which gives us a path to retune.
  - The LLM narrative is downstream of the deterministic layer, so
    poor scoring upstream produces poor narratives downstream. Hard
    to debug "the scoring is fine but the narrative is wrong".
- **Neutral**:
  - The split is mirror-able: a future "LLM-only narrative" mode
    could read the same `CorrelatedView` object and produce a
    different narrative format.

## Alternatives Considered

- **End-to-end LLM**: rejected as above. Would not survive diligence.
- **Pure deterministic rules with template-based narrative**: rejected
  — buyer-facing narratives need the LLM's fluency. Template narratives
  read like 2010s-era trading-bot output.
- **Single-layer "LLM with retrieval grounding"**: deferred — the
  retrieval-augmented pattern is still LLM-in-the-loop for scoring,
  which we explicitly do not want.

## References

- Deterministic layer: `lib/correlator/{sources,scoring,engine}.py`
- Narrative layer: `lib/synthesis/{narrative_engine,rubric,prompts}.py`
- Property tests (Tranche 6 Lane 1):
  `tests/property/test_correlator_scoring_properties.py`
- Runbooks:
  - `docs/ops/signal-correlator-runbook.md`
  - `docs/ops/narrative-synthesis-runbook.md`
  - `docs/ops/narrative-eval-runbook.md`
