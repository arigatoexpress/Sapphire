# Vertex / Gemini Eval Harness Runbook

The Vertex / Gemini eval harness is a Sapphire plugin tool that benchmarks
Gemini OODA outputs against the local 4-tier inference mesh and a deterministic
mock baseline. The point is to let the operator answer one question with a
reproducible artifact: **is the Google AI Plus / Vertex spend actually buying
us better reasoning than what we already run for free?**

The tool sits beside `gemini_ooda` in the "AI complement" lane of the registry.
It is internal-only, dry-run-default, and treats every live Gemini call as
spend that has to be justified by a rubric delta.

## Purpose and audit posture

Every external-AI lane in Sapphire ships with three guarantees:

1. The default path produces a useful answer without spending a single token.
2. The live path is gated by `SAPPHIRE_GEMINI_LIVE=1`, a sensitivity
   classifier, and hard per-hour, per-month, and per-run token caps.
3. Outputs carry a versioned provenance envelope so an external auditor can
   re-run the rubric on the same artifacts and get identical scores.

`vertex_eval` is the audit harness for guarantee three. Without it, "Gemini
gave us better answers" is a vibe; with it, "Gemini scored +0.15
structural_validity and +0.07 citation_density on the
`crypto-regime-shift` set with a +1,200ms latency penalty for $0.0006" is a
defensible claim.

## Inputs

The tool reads a JSON object on stdin. The supported actions are:

| Action       | What it does                                                      |
|--------------|-------------------------------------------------------------------|
| `eval`       | Run a prompt set against the dry-run baseline; report rubric scores per prompt and aggregate. In live mode, also runs the same set through Gemini and reports the live aggregate alongside. |
| `compare`    | Run the same prompt set against (i) Gemini live (if gated), (ii) the local mesh `balanced` tier via the inference proxy, and (iii) the deterministic mock baseline. Returns aggregate deltas per generator. |
| `prompt-set` | List the canonical eval prompt sets bundled in the tool. No I/O. |
| `status`     | Show counters, run-artifact count, last-run timestamp. Never contacts Google or the local mesh. |

Optional fields:

```jsonc
{
  "action": "compare",
  "set_name": "crypto-regime-shift",     // or "vote-monitor-context", etc.
  "prompt_ids": ["crypto-regime-shift-01"],  // narrow to specific cases
  "mode": "live",                         // "dry-run" (default) or "live"
  "model": "gemini-2.5-flash",
  "local_model_alias": "balanced",
  "proxy_url": "http://127.0.0.1:11435/v1/chat/completions",
  "max_output_tokens": 512
}
```

## Output format

`eval` and `compare` return a JSON object with `action`, `metadata`,
`generators`, and (for `compare`) `deltas`, plus a `provenance` block.
`metadata` always reports `mode_requested`, `mode_actual`, `model`,
`prompt_count`, `sensitive_cases`, and a `run_id`. Each entry under
`generators` has its name, an `aggregate` summary, and a `per_prompt`
list of records:

```jsonc
{
  "prompt_id": "vote-monitor-context-01",
  "set_name":  "vote-monitor-context",
  "topic":     "Blackhole ve(3,3) bribe efficiency drift",
  "generator": "gemini-live",
  "rubric": {
    "structural_validity": 1.0,
    "actionability":       0.75,
    "citation_density":    0.42,
    "latency_ms":          812,
    "tokens_used":         410,
    "caps_breach":         false,
    "notes":               []
  },
  "error":         null,
  "response_keys": ["act","decide","observe","orient"]
}
```

The artifact is also written to `~/.cache/sapphire/vertex_eval/runs/<run_id>.json`
with a sidecar envelope at `<run_id>.json.envelope.json` so the file itself can
be replayed by `python3 scripts/ops/provenance_verify.py --pretty`.

## Dry-run vs live

Live calls only happen when **all** of these are true:

1. `SAPPHIRE_GEMINI_LIVE=1` is set in the calling environment.
2. The bundled prompt set passes the sensitivity classifier (no API keys,
   customer PINs, internal mesh IPs, position sizes, etc.).
3. `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is present in
   `~/.sapphire/secrets.env` or the environment.
4. The hourly call cap (`MAX_CALLS_PER_HOUR = 8`) has not been hit.
5. Adding the projected token cost would not exceed
   `MAX_TOKENS_PER_MONTH = 500_000`.
6. The prompt set fits under `EVAL_PROMPTS_PER_RUN_HARD = 12`.

If any check fails, the tool falls back to the dry-run mock with
`mode_actual` set to one of: `dry-run`, `dry-run-blocked-by-env`,
`dry-run-safety`, `dry-run-no-key`, `dry-run-rate-limited`, or
`dry-run-live-error`. A sensitive case anywhere in the set forces the
whole run into `dry-run-safety`.

## Caps

| Cap                              | Default   | Source of truth                        |
|----------------------------------|-----------|----------------------------------------|
| Per-call output tokens           | 4096 hard | `MAX_OUTPUT_TOKENS_HARD` in `lib/eval/vertex_harness.py` |
| Per-call input chars             | 12_000    | `MAX_INPUT_CHARS_HARD`                 |
| Calls per hour                   | 8         | `MAX_CALLS_PER_HOUR`                   |
| Tokens per month                 | 500_000   | `MAX_TOKENS_PER_MONTH`                 |
| Prompts per run                  | 12 hard   | `EVAL_PROMPTS_PER_RUN_HARD`            |

The constants live in `lib/eval/vertex_harness.py` and are re-exported by the
plugin tool. Bumping them in source keeps the cap enforceable at module
import; runtime overrides are intentionally not supported.

## How to interpret the rubric

Three rubric scores are floats in [0, 1]; the rest are passthrough integers
or booleans.

- `structural_validity` — does the output parse as a four-section OODA
  packet (`observe`, `orient`, `decide`, `act`)? Missing keys cost 0.25
  each. Empty values count as missing.
- `actionability` — does the `act` section contain at least two concrete
  steps starting with action verbs? Two valid steps map to 0.5; four or
  more map to 1.0.
- `citation_density` — ratio of "claims" to "citations" inside
  `observe + orient + decide + act`. Citations include markdown links and
  numeric facts (percentages, currency, durations). Claims are sentences.
  Capped at 1.0.
- `latency_ms` and `tokens_used` are raw observed numbers. Use them to
  decide whether a Gemini-versus-mesh delta is worth the cost.
- `caps_breach` is a boolean — true if this single response would have
  exceeded the per-call output-token or input-char hard caps. The harness
  refuses to run a batch that breaches the per-run prompt cap.

The `aggregate` payload reports `_mean`, `_min`, `latency_ms_mean`,
`tokens_used_total`, and `caps_breach_count`. Compare aggregates across
generators in the `deltas` block; positive deltas mean the first generator
beat the second on that metric (lower latency is a better delta only when
you want it to be — read the dimension carefully).

## Soak posture

The tool is internal and not yet wired to a scheduled task. The expected
soak path is:

1. Land this PR with all four local verifications green
   (`ruff`, plugin pytest, core pytest, `production_readiness_sweep.py`).
2. Run `eval` once a week in dry-run mode to confirm the rubric is stable
   against the bundled prompt sets.
3. Once live spend is authorised, run `compare` against `crypto-regime-shift`
   and review the deltas; promote to a weekly `[CLOUD]` routine only if the
   live-versus-local delta is reproducible and material.
4. After 30 days of clean dry-run traffic plus at least one authorised live
   run, consider adding a LaunchAgent that invokes `eval` weekly and writes a
   provenance-stamped artifact to `data/.autonomy/vertex-eval/<YYYY-MM-DD>.json`.

## Acceptance tests

```bash
python3 -m pytest tests/unit/test_vertex_eval_harness.py -q
python3 -m pytest plugins/claw-sapphire/tests/test_vertex_eval.py -q
```

The harness module is covered by 17 unit tests; the plugin tool by 16
plugin tests covering the dry-run path, the live env gate, the sensitivity
gate, the rate cap, the deterministic mock, the run-artifact provenance
envelope, and the stdin/stdout main entry point.

## Why this exists

Every external-AI commitment in Sapphire is a recurring spend until proven
otherwise. The eval harness is the tool an auditor or buyer uses to answer
"is the Vertex spend buying us anything?" with a reproducible artifact, on
a no-spend default. The dry-run baseline is intentionally simple so the
score delta tracks the live model's actual contribution rather than the
operator's prompting craft.
