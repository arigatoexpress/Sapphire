# ADR 0004 — Bounded LLM tools via env-flag-gated live path

- **Status**: accepted
- **Date**: 2026-04-28
- **Authors**: Sapphire ops
- **Related**: ADR 0005, ADR 0008

## Context

Sapphire integrates LLM-driven tools (Gemini OODA, Vertex eval, narrative
synthesis, customer-API surfaces, dossier generation, etc.) where the
"live" path makes external API calls that:

- Cost real money (Vertex tokens, Moonshot/Kimi, OpenAI, Anthropic API).
- Can leak signal IP if the prompt body contains correlated signals or
  trade reasoning.
- Have rate-limit surfaces that can be exhausted by a runaway loop.
- Need credentials that the operator does not want shipped into CI fixtures
  or into autonomous tranches.

Without a discipline, every new LLM tool ships either (a) blocked entirely
because the operator can't audit the live path, or (b) running live by
default, where any test or scheduled-task drift will burn tokens.

## Decision

Every LLM-touching tool follows a **dry-run-default + explicit env flag**
pattern. The canonical shapes are:

- `gemini_ooda` (`plugins/claw-sapphire/tools/internal/gemini_ooda.py`):
  default returns deterministic mock output; `SAPPHIRE_GEMINI_LIVE=1`
  enables real Vertex calls.
- `vertex_eval` (`plugins/claw-sapphire/tools/internal/vertex_eval.py`):
  default returns a structured eval skeleton; `SAPPHIRE_VERTEX_EVAL_LIVE=1`
  enables real eval invocation.
- `narrative_synthesis` (`lib/synthesis/narrative_engine.py`): default uses
  a deterministic-rules fallback; `SAPPHIRE_NARRATIVE_LIVE=1` engages the
  LLM path.

**Required components for any new LLM tool:**

1. **A pure-deterministic mock-default code path** that returns realistic
   shape (right field names, right types). Tests run against this path.
2. **An env-flag gate** named `SAPPHIRE_<TOOL>_LIVE=1`. Default is unset,
   so the live path is dormant.
3. **Cached counters** under `~/.cache/sapphire/<tool>/` for rate limiting.
4. **Per-call provenance envelope** (see ADR 0005) emitted regardless of
   live vs mock path.
5. **A runbook** at `docs/ops/<tool>-runbook.md` covering the live-mode
   bring-up checklist (secrets, quotas, kill switch).

Tests must NOT set `SAPPHIRE_<TOOL>_LIVE=1`. Live runs are operator-
driven only.

## Consequences

- **Positive**:
  - Zero accidental token spend in CI or scheduled tasks. Verified across
    Tranches 3-5.
  - Tests are deterministic; mock outputs are versioned and reproducible.
  - Live mode can be toggled per-tool — one tool can be live while
    another stays mocked.
  - The same pattern handles "this surface needs operator approval before
    live" cleanly (Lane 1 live capital ledger, Lane 7 customer API).
- **Negative**:
  - Two code paths per tool means double the surface. Drift is a real
    risk: the mock path can fall out of sync with the live response
    shape. We mitigate via integration tests that run the live path
    behind the env flag in operator-supervised soaks.
  - Mock-default changes the contract semantics: callers cannot
    distinguish "no LLM available" from "LLM returned this exact mock
    output". We add a `mock=true` field to mock responses to make this
    visible.
  - New developers must learn the pattern; it is not enforced by a
    framework. Hooks could enforce it but currently do not.
- **Neutral**:
  - Per-call provenance envelopes (ADR 0005) apply to both paths.
  - Sensitivity classifier (`plugins/claw-sapphire/lib/sensitivity_classifier.py`)
    runs on both paths.

## Alternatives Considered

- **Live-by-default with rate-limit caps**: rejected — a single test
  drift could burn the whole month's budget before the cap fires.
- **No mock; tools fail-closed when env flag unset**: rejected — makes
  unit tests painful and forces operators to populate secrets to run
  any local verification.
- **A single feature flag (`SAPPHIRE_LLM_LIVE=1`) covering all tools**:
  rejected — too coarse; we want to soak one tool at a time before
  enabling another.

## References

- Canonical implementations:
  - `plugins/claw-sapphire/tools/internal/gemini_ooda.py`
  - `plugins/claw-sapphire/tools/internal/vertex_eval.py`
  - `lib/synthesis/narrative_engine.py`
- Runbooks:
  - `docs/ops/gemini-ooda-daily-runbook.md`
  - `docs/ops/vertex-eval-runbook.md`
  - `docs/ops/narrative-synthesis-runbook.md`
- Sensitivity gate:
  `plugins/claw-sapphire/lib/sensitivity_classifier.py`
