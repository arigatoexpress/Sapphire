# Sapphire test-rigor 0.1.0 — property-based + mutation testing pass

Version 0.1.0. Tranche 6 Lane 1. 2026-04-29. Author: Sapphire engineering, autonomous dispatch.

## Why this exists

Sapphire's autonomy story has, by the start of Tranche 6, accumulated 5,275+
collected unit tests across the core repo and plugin tree. That is a lot of
example-based coverage. It is also, structurally, a thin layer on top of an
ever-growing pure-logic surface — PII redaction (a non-negotiable buyer-facing
contract), correlator scoring (the trade gate), Sortino computation (the live-
capital ramp gate), observability aggregation (the dashboard buyers see), and
the audit panel heuristics (the autonomous merge gate). The example-based
tests pin known-good cases. They are blind to the inputs we never thought to
write.

Mutation testing and property-based testing fill that gap from two opposite
ends:

- **Property-based testing** generates many examples per run, focused on
  invariants the code must hold across the *entire* input domain (not just
  the dozen we coded up). It is cheap on time but high in surprise value.
- **Mutation testing** modifies the source under test (e.g. flip an
  inequality, swap a constant) and re-runs the test suite. If the suite
  still passes after a meaningful mutation, the test suite has a coverage
  gap precisely where the mutation lived. It is slow (hours per module) but
  yields exactly the gap report.

Together they pin down a more durable kind of correctness than what either
alone can provide. This product surface does both, scoped narrowly enough
that the maintenance overhead stays in proportion to the trust we want to
buy from operators and (eventually) external diligence reviewers.

## Scope

Five modules — exactly the surface that buyer-facing surfaces depend on, and
that the trading critical path depends on:

| Module | Why it matters |
| --- | --- |
| `lib/security/pii_redactor.py` | Customer-dossier output goes to Palantir / Robinhood corp-dev. PII leakage is the only failure mode that matters. |
| `lib/correlator/scoring.py` | The gate function that turns N heterogeneous source signals into one ``edge_score``. Out-of-bounds outputs propagate to sizing and kill-switch. |
| `lib/live_portfolio/sortino.py` | The metric the live-capital ramp gate uses to advance from $5 → $50 → $500 rungs. A subtle bug here either over-promotes capital or stalls the soak. |
| `lib/live_portfolio/ramp_gate.py` | Wraps `sortino` with the trading-day clock and operator-gate check. Mutation testing surfaces date-arithmetic edge cases. |
| `lib/audit_panel/heuristics.py` | The set of heuristics that decide whether a freshly merged PR needs human review. False negatives leak risk; false positives waste operator attention. |

We deliberately do NOT widen the surface to whole-repo mutation testing in
this PR. Mutation testing on a 50k-line repo takes days, not hours, and the
signal is dominated by noise from auto-generated / vendored modules. We re-
visit that decision after this 0.1.0 lands and the operator workflow proves
useful.

## Surface

### Property-based test files

All under `tests/property/` (new directory).

- `test_pii_redactor_properties.py` — 20 properties, plus 1 documented
  found-bug `xfail`. Covers idempotence (`redact(redact(x)) == redact(x)`),
  monotone scrubbing (never increases sensitivity), locale stability
  (NFC/NFD, CJK, diacritics), public-surface dispatch (`redact()` always
  returns a value of the right shape), and empty/None placeholder
  guarantees.

- `test_correlator_scoring_properties.py` — 14 properties. Pin
  ``-1 <= edge_score <= +1`` over the full input lattice; symmetry under
  direction flip; agreement-bonus monotonicity in number of corroborating
  sources; freshness factor monotone-decreasing in age and bounded in
  ``[0, 1]``; deterministic byte-identical output; safe handling of
  unknown source names.

- `test_live_portfolio_sortino_properties.py` — 9 properties. Most-
  important: the Sortino value matches an independent reference
  implementation (manually re-derived from the docstring formula) to
  ``rel_tol=1e-6`` over 100 random series of 14-200 samples. Also:
  small-sample shortfall (always ``value=None`` with reason
  ``insufficient_periods``); all-zero series (``no_downside_no_positive_excess``);
  all-positive series (``inf``); ``last_n_sortino`` only consumes the tail.

- `test_observability_aggregator_properties.py` — 8 properties. Snapshot
  serializes deterministically (modulo `uptime_seconds` which tracks the
  real clock); the JSON envelope is bounded under 1 MB; no `$HOME` path
  ever leaks; the schema-required top-level keys are always present;
  the slim ``stream-rates`` endpoint agrees with the corresponding section
  of the full snapshot field-for-field.

- `test_audit_panel_heuristics_properties.py` — 18 properties. Each
  heuristic is monotone in its trigger (more signal → still trips, less →
  no trip); a synthetic-clean PR fixture passes every heuristic; the
  Markdown reporter never echoes a credential signature in cleartext;
  evidence is always bounded under `MAX_EVIDENCE_ITEMS`; severity
  ordering is stable.

**Total: 69 property tests, plus 1 xfail tracking the documented
bug-found case.**

### Hypothesis profiles

Three profiles registered in `tests/property/__init__.py`:

- `default` — 100 examples per property. Suitable for `make test`.
- `ci` — 500 examples per property. Opt-in via `HYPOTHESIS_PROFILE=ci`
  before the heavier "release readiness" sweeps.
- `fast` — 25 examples per property. Useful for tight inner-loop
  iteration when changing the property text itself.

The profile is selected at import time; activate with
`HYPOTHESIS_PROFILE=ci python3 -m pytest tests/property/`.

### Mutation testing wrapper

`scripts/ops/run_mutation_testing.py` wraps `mutmut run` against the curated
target list. Live runs are operator-gated by `SAPPHIRE_MUTATION_TEST_LIVE=1`
or `--force-live`. Without the gate, the runner stays in dry-run mode and
emits the command sequence it would invoke, plus a dry-run report so
downstream tools can wire against the schema without spending the live
runtime cost.

JSON sidecar: `data/test_rigor/mutation_report_<YYYY-MM-DD>.json` (schema
version 1). Markdown summary: printed to stdout for paste-into-Telegram.

Dry-run unit tests: `tests/unit/test_run_mutation_testing_dryrun.py` (11
cases — well above the 6-case minimum the lane spec asked for).

## Authorized dependencies

This lane is authorized to add exactly two new entries to
`requirements-test.txt`:

- `hypothesis>=6.130,<7`
- `mutmut>=2.5,<3`

These are test-only deps. They do NOT bleed into runtime requirements files
under `services/` or `lib/`.

## Found bugs

### Found bug #1 — non-alphanumeric leading email locals lose idempotence

**Severity**: low. No raw PII leakage; benign domain-info loss only.

Hypothesis surfaced this on the very first run. The minimal failing example
(after shrinking) is `_alice@example.com`. The redactor produces
`_***@example.com`, which is a correct first-pass redaction. But on the
second pass, the recogniser regex `_REDACTED_EMAIL_RE` only accepts a
prefix from `[A-Za-z0-9]{1,2}` — underscore (and `+`, `.`, `-`) are not in
that class. So the second-pass walker mis-classifies the redacted form as
an unparsable email and emits the generic `<redacted>@<redacted>`
placeholder, losing the domain triage signal.

The bug is documented in
`tests/property/test_pii_redactor_properties.py::test_redact_email_idempotence_with_special_first_char_xfail`
as an `@pytest.mark.xfail(strict=False)` test. The fix is a trivial
recogniser regex widening: replace `[A-Za-z0-9]{1,2}` with
`[A-Za-z0-9._+-]{1,2}` in the `_REDACTED_EMAIL_RE` pattern. We do not ship
the fix in this PR because (a) the lane is scoped to test rigor, not
behavior changes; (b) we want the xfail to remain green so future
regressions on the same-shape input get caught. A follow-up PR will widen
the recogniser and remove the xfail mark.

The follow-up issue title (suggested): `fix(security): pii_redactor email
idempotence on non-alphanumeric leading char`.

## Limitations

1. **Mutation testing is operator-supervised**. We will not run mutation
   tests in CI — the runtime is hours and the value/cost ratio is wrong
   for every-PR coverage. The wrapper exists so the operator can launch a
   targeted run when changing one of the five tracked modules, paste the
   resulting Markdown into a PR comment, and audit the surviving mutants.

2. **Property tests run with 100 examples by default**. The `ci` profile
   bumps to 500. Hypothesis's example database (under `.hypothesis/`) is
   gitignored — found regressions are persistent within a single dev
   environment but not shared across machines. We rely on the property
   text itself (and the documented xfail above) to record found bugs.

3. **Reference Sortino implementation duplicates the formula**. The
   property-test reference is a from-scratch port of the docstring formula.
   If both implementations are wrong the same way, the property silently
   passes. We treat this as acceptable because (a) the docstring formula
   is a citation of an external authority, not a Sapphire invention; (b)
   small-sample / all-zero / all-positive behaviour gets pinned by
   separate properties using simpler proofs.

4. **Observability aggregator determinism excludes `uptime_seconds`**.
   The aggregator pulls `kern.boottime` via `sysctl`; we cannot pin that
   without further refactoring the aggregator to inject the uptime probe.
   The exclusion is documented in the property body; everything else
   serializes byte-identically across runs.

5. **No mutation testing of `lib/audit_panel/scorer.py` or `reporter.py`**.
   These two are pure transformation layers over `heuristics.py` outputs;
   their bugs would surface as differences in the reporter Markdown
   property assertions. Adding them to `MUTATION_TARGETS` is straightforward
   and is on the follow-up list.

## How to run

```bash
# All property tests, default 100 examples per property.
python3 -m pytest tests/property/

# CI-grade depth (500 examples per property; ~5x runtime).
HYPOTHESIS_PROFILE=ci python3 -m pytest tests/property/

# Mutation testing dry-run — emits planned commands + JSON sidecar.
python3 scripts/ops/run_mutation_testing.py

# Mutation testing live (hours of runtime) — operator-gated.
SAPPHIRE_MUTATION_TEST_LIVE=1 python3 scripts/ops/run_mutation_testing.py

# Run mutation testing against ONE module.
SAPPHIRE_MUTATION_TEST_LIVE=1 python3 scripts/ops/run_mutation_testing.py \
    --module lib/security/pii_redactor.py
```

## Acceptance gate

This 0.1.0 ships when:

1. All 69 property tests pass at `HYPOTHESIS_PROFILE=default` (100 examples).
2. The 11 dry-run unit tests for `scripts/ops/run_mutation_testing.py` pass.
3. The found-bug xfail (`test_redact_email_idempotence_with_special_first_char_xfail`)
   is green — it MUST stay xfail until the follow-up fix lands.
4. The repo-wide `pytest tests/unit/ --tb=short -q` baseline is unaffected
   (no new failures, no new collection errors).

## Future work

- **0.2.0**: widen the mutation-testing target list to add `scorer.py` and
  `reporter.py`. Add a per-mutant survivor-aging policy to the JSON
  sidecar so operators can see which mutants stayed alive across N
  consecutive runs.
- **0.3.0**: integrate the mutation report into the daily evening digest
  (`docs/ops/evening-digest-runbook.md`) so the operator sees a delta
  rather than having to remember to invoke the runner manually.
- **0.4.0**: lift the property test database (`.hypothesis/`) into a
  shared S3/GCS artifact so found regressions are durable across
  developer machines and CI runs. Today they are local-only.

## Cross-references

- Operations runbook: `docs/ops/test-rigor-runbook.md`
- Wave-2 sister lanes: time-travel testing (Lane 3), walk-forward testing
  (Lane 5). Conflict surface should be near-zero — this lane only modifies
  `requirements-test.txt` outside the new `tests/property/` directory.
- Hypothesis docs: <https://hypothesis.readthedocs.io/en/latest/>
- Mutmut docs: <https://mutmut.readthedocs.io/en/latest/>
