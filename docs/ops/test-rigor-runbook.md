# Test rigor runbook (property-based + mutation testing)

Operational counterpart to `docs/products/test-rigor-0.1.0.md`. This doc is
the "what to do when" reference for operators running, interpreting, and
acting on the property-based + mutation testing surface.

## When to run what

| Scenario | Property suite | Mutation runner |
| --- | --- | --- |
| Every `make test` invocation | Default profile (100 examples) | n/a (operator-only) |
| PR readiness sweep before opening a PR that touches one of the five tracked modules | `HYPOTHESIS_PROFILE=ci python3 -m pytest tests/property/<module>_properties.py` | `SAPPHIRE_MUTATION_TEST_LIVE=1 python3 scripts/ops/run_mutation_testing.py --module <path>` |
| Weekly readiness sweep | `HYPOTHESIS_PROFILE=ci python3 -m pytest tests/property/` | Full run on Sunday from a quiet workstation |
| Buyer-meeting prep / diligence packet refresh | Both | Both |
| Investigating a falsifying example you just saw | Targeted re-run with `--hypothesis-seed=<seed>` | n/a |

## Daily / per-PR loop

1. Make your code change.
2. Run the local default-profile sweep:

   ```bash
   python3 -m pytest tests/property/ -q
   ```

   100 examples per property. Should complete in under 10 seconds for the
   full suite of 69 tests.

3. If you touched one of the five tracked modules — `pii_redactor.py`,
   `scoring.py`, `sortino.py`, `ramp_gate.py`, `heuristics.py` — also run
   the corresponding property file at the CI profile:

   ```bash
   HYPOTHESIS_PROFILE=ci python3 -m pytest \
       tests/property/test_<module>_properties.py -q
   ```

   500 examples per property — typically 30-60 seconds for one module.

4. If the run surfaces a falsifying example, **save the seed and the
   shrunk input**. Hypothesis prints both. Treat the result like any
   other test failure: either fix the production bug, narrow the
   property's input strategy with documented justification, or mark the
   property `@xfail(strict=False)` with a follow-up issue link.

## Weekly readiness sweep

Recommended cadence: Sunday afternoon, from a quiet workstation. Mutation
testing pegs the laptop's CPU for hours, so plan accordingly.

```bash
# 1. Property sweep at CI depth
HYPOTHESIS_PROFILE=ci python3 -m pytest tests/property/ -v

# 2. Mutation testing — full target list
SAPPHIRE_MUTATION_TEST_LIVE=1 python3 scripts/ops/run_mutation_testing.py

# 3. Inspect the report
cat data/test_rigor/mutation_report_$(date +%Y-%m-%d).json | jq '.modules[] | {module, kill_rate, survived}'
```

The Markdown summary (printed by the runner at completion) is paste-safe
for Telegram. Recommended: paste the table into the Sapphire ops channel
along with the JSON sidecar path.

## Reading the mutation report

Each module entry has these fields:

```json
{
  "module": "lib/security/pii_redactor.py",
  "killed": 234,
  "survived": 6,
  "timeout": 1,
  "suspicious": 0,
  "skipped": 0,
  "total": 241,
  "kill_rate": 0.971,
  "elapsed_seconds": 8923.4,
  "mode": "live",
  "command": [...]
}
```

Reading guide:

- **`kill_rate >= 0.95`**: healthy — the test suite catches > 95 % of
  mutations. Good enough for an autonomous-merge module. No action.
- **`kill_rate >= 0.80, < 0.95`**: review survivors. Some are usually
  equivalent mutants (mathematically identical to the original); flag
  the rest as a coverage gap and add a focused unit or property test.
- **`kill_rate < 0.80`**: meaningful coverage gap. Triage every
  surviving mutant. Open a tracking issue. Do not advance the module
  to a higher autonomy tier until the rate recovers.
- **`timeout > 0`**: a mutated form caused tests to take 2x+ as long.
  Usually a benign infinite-loop guard but worth eyeballing the diff
  via `mutmut show <id>`.

To inspect surviving mutants directly:

```bash
# List all survivors for the most recent run
python3 -m mutmut results

# Show the diff for one
python3 -m mutmut show 42

# Apply one to disk for interactive testing
python3 -m mutmut apply 42

# Revert (just re-checkout the file)
git checkout -- lib/security/pii_redactor.py
```

## Adding a new property test

1. Create a new test in the appropriate file under `tests/property/`. If
   the module is not in the existing file set, add a new
   `test_<module>_properties.py` file alongside the others.
2. **Import `tests.property` to load the hypothesis profile**:

   ```python
   import tests.property  # noqa: F401
   ```

3. Use the most precise strategy possible. Wide strategies generate more
   noise than signal. If your invariant only holds for "non-empty
   strings", use `st.text(min_size=1)` instead of `st.text()`.
4. Always include a docstring on the test that names the invariant.
5. Property tests should be **fast** (<1 ms per example). If a property
   takes longer, it is probably exercising too much surface — narrow
   the strategy or split into multiple properties.

## Adding a new mutation testing target

1. Identify the module to add. Criteria:
   - Pure logic (no I/O dependencies that mutmut can't exercise).
   - Exercised by a fast unit + property test pair.
   - Buyer-facing or trading-critical.
2. Add an entry to `MUTATION_TARGETS` in
   `scripts/ops/run_mutation_testing.py`. Tuple shape:
   `(source_path, (test_path_1, test_path_2, ...))`.
3. Update the dry-run unit tests:
   `tests/unit/test_run_mutation_testing_dryrun.py` — the
   `test_dry_run_emits_command_for_every_target` test will now expect
   one more entry.
4. Run a dry-run + live invocation to confirm the kill rate.

## Troubleshooting

### Hypothesis: "FailedHealthCheck: data generation is too slow"

Either widen the strategy filter or bump the deadline. The default
profile in `tests/property/__init__.py` already suppresses
`HealthCheck.too_slow`; if you see this anyway, the per-test
`@hyp_settings(suppress_health_check=[HealthCheck.too_slow])` decorator
overrides it and is the right local fix.

### Hypothesis: "FailedHealthCheck: filter_too_much"

Your `.filter()` predicate rejects too many generated inputs. Refactor
to use `st.composite` and generate valid inputs directly instead of
filtering invalid ones out.

### Mutmut: "test runner has timed out"

The runner default timeout is 60 seconds per mutation. Long-running
tests blow this up. Either narrow the test path passed to
`--paths-to-mutate` (so only the fast tests run per mutant) or
configure a longer timeout via `mutmut.timeout` in `pyproject.toml`.

### Mutmut: "subprocess pickle error" on Apple Silicon

Mutmut 2.5 hit an upstream pickle bug on certain Python 3.12+
configurations on M-series Macs. Workaround: pin
`PYTHONNOMULTIPROCESSING=1` in the environment. The runner script
already sets `--CI` which serializes mutation testing.

### "Found bug" xfail unexpectedly passing

The `xfail(strict=False)` in
`test_redact_email_idempotence_with_special_first_char_xfail`
documents a known idempotence gap on non-alphanumeric leading email
local parts. If this test starts passing, that means someone fixed the
recogniser regex — promote the xfail to a regular test, remove the
mark, and close the follow-up issue.

## Where to escalate

- **Property test surfaces a real bug**: fix it in a separate PR. Do
  not bundle the fix into a property-test PR — keeping behavior changes
  separate from test rigor changes makes the diff legible.
- **Mutation kill rate falls below 0.80 on a module**: that's a coverage
  gap; raise it as a routine review item with the operator. Do not
  silently let an autonomous-merge module degrade.
- **Mutation runner reports `error: command not found: mutmut`**: the
  test deps drifted. Re-run `pip install -r requirements-test.txt` to
  pull `mutmut>=2.5,<3`.

## Pre-merge checklist (test-rigor 0.1.0 PR)

- [ ] `python3 -m pytest tests/property/` — 69 passed, 1 xfailed.
- [ ] `python3 -m pytest tests/unit/test_run_mutation_testing_dryrun.py` —
      11 passed.
- [ ] `python3 scripts/ops/run_mutation_testing.py --print-only` — runs
      without raising; emits Markdown.
- [ ] `python3 -m pytest tests/unit/ -q --no-header` — baseline test
      count unchanged (no regressions in unrelated tests).
- [ ] PR body lists `hypothesis` and `mutmut` as the two test-only deps
      authorized for THIS lane.
- [ ] Commit messages all carry `[skip ci]` per Tranche 6 spend posture.

## On-call: nothing to do

Property-based + mutation testing are a *development-time* aid. They do
not run in production, do not ship logs anywhere, do not page anyone.
There is no on-call escalation path; the only operator action is the
weekly mutation-testing readiness sweep above.

## Quick links

- Source of truth: `tests/property/`.
- Runner: `scripts/ops/run_mutation_testing.py`.
- Schema: `data/test_rigor/mutation_report_<date>.json` (schema_version 1).
- Product surface doc: `docs/products/test-rigor-0.1.0.md`.
- Hypothesis profiles: `tests/property/__init__.py`.
- Mutmut configuration: defaults; no `[tool.mutmut]` block in
  `pyproject.toml` yet.
