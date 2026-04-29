# ADR 0006 — Fixture-clock vs impl-clock date-flake test template

- **Status**: accepted
- **Date**: 2026-04-28 (originally), codified 2026-04-29
- **Authors**: Sapphire ops
- **Related**: PR #377, PR #394, ADR 0002

## Context

Sapphire's test suite has crossed 5,000 cases. Many tests use timestamp
fixtures (`now - 1h`, `score_news()` with a fixed `NOW` constant, etc.)
that interact with implementation code that itself reads `datetime.now()`
or `time.time()`. When the fixture's notion of "now" disagrees with the
implementation's notion of "now", tests pass on the day they were written
and flake on:

1. **Day-boundary crossings** — a test fixture built from `now - 1h` at
   00:32 local fell on the previous local day; an impl that compared
   `today()` against the fixture filtered the row out as "yesterday".
   First hit: PR #377 (`test_dev_pulse`).
2. **Aging fixtures** — a test using a fixed `NOW = datetime(2026, 4, 1)`
   constant calls an impl that filters rows older than 24h against the
   real clock. After Apr-1 + 30 days, the impl's "real now" is past the
   fixture's "freshness" cutoff. First hit: PR #394
   (`test_score_news_now_defaults_to_current_time`).
3. **Production-readiness sprint cases** — a third instance during the
   Tranche 4 production-readiness sprint (correlator scoring tests).

The flake mode is not "always fails" — it's "fails only at certain
absolute times". CI green at noon UTC, red at 23:59 UTC. Operationally
expensive to debug.

## Decision

When a test uses any of `datetime.now()`, `date.today()`, `time.time()`
to build a fixture **and** the implementation under test reads its own
clock, we adopt one of two patterns:

### Pattern A — Inject the clock as an argument

The implementation function takes a `now: datetime` argument with a
default of `datetime.now(UTC)`. The test passes the same anchor that
built the fixture:

```python
def score_news(items, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    ...

def test_score_news_now_defaults_to_current_time(self):
    NOW = datetime(2026, 4, 1, tzinfo=UTC)
    item = {"published_at": NOW - timedelta(hours=1), ...}
    result = score_news([item], now=NOW)  # explicit anchor
    assert result["score"] > 0
```

This is the preferred pattern for new code.

### Pattern B — Monkey-patch the impl's clock with FrozenDatetime

When the implementation is upstream / not modifiable, monkey-patch
`datetime` in the impl's namespace with a `FrozenDatetime` subclass:

```python
class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 4, 1, tzinfo=tz or UTC)

def test_dev_pulse_collect(monkeypatch):
    monkeypatch.setattr("plugins.claw_sapphire.tools.dev_pulse.datetime",
                        FrozenDatetime)
    ...
```

The fixture is then built relative to the same anchor.

### Detection guideline

When writing or modifying any test that uses a clock primitive, ask:
**"if this runs at 00:32 local on the next day OR if days have passed
since the fixture constant was written, does the assertion still
hold?"**

If the answer is "no", the test must use Pattern A or Pattern B. The
`feedback_multi_repo_workflow.md` memory entry (section
"Fixture-clock vs impl-clock") is the durable reference.

## Consequences

- **Positive**:
  - Eliminates a known flake class. Three confirmed instances fixed
    (#377, #394, production-readiness sprint).
  - Cheap retrofit: most cases need ≤ 5 lines of test changes.
  - Pattern A produces cleaner production code (explicit clock as
    dependency) — net win even setting tests aside.
- **Negative**:
  - Pattern B (monkey-patch) is fragile against module-import-order
    changes; if the test imports the impl before patching, the patch
    misses. Tests must monkey-patch the **impl's** namespace, not
    `datetime` globally.
  - Two patterns mean code review must distinguish which applies; new
    contributors sometimes pick the wrong one.
  - Does not catch tests that use `time.time()` indirectly via mocked
    services (e.g. requests-mock).
- **Neutral**:
  - Existing tests that don't have the disagreement (e.g. tests using
    constant fixtures against non-clock impls) are unaffected.

## Alternatives Considered

- **Freeze the system clock at test-collection time
  (`pytest-freezegun`)**: rejected — adds a runtime dep and changes
  global behavior in surprising ways.
- **Hard-fail any test using `datetime.now()`**: rejected — too broad;
  many legitimate tests use `now()` for non-fixture purposes.
- **A custom pytest plugin that detects fixture-clock-vs-impl-clock
  drift**: deferred — the patterns above cover the cases; a plugin
  is over-engineering for the volume.

## References

- Originating PRs: PR #377, PR #394
- Memory entry:
  `~/.claude/projects/-Users-aribs/memory/feedback_multi_repo_workflow.md`
  (section "Fixture-clock vs impl-clock date-flake template")
- Canonical example: `tests/unit/test_dev_pulse.py::test_collect_trading_status_reads_signals_and_portfolio`
- Canonical example: `tests/unit/test_control_plane_scoring.py::test_score_news_now_defaults_to_current_time`

## Related — property test catalog (Tranche 6 Lane 1)

The Tranche 6 property-based testing pass (`tests/property/`) treats clock
discipline as a first-class invariant. Every property test in that catalog
that touches a clock primitive applies Pattern A (inject the clock). The
catalog as of 2026-04-30 (≥ 80 properties + 1 `xfail` documenting a real bug
in the PII redactor):

| File | Properties | Clock-aware |
|---|---:|---|
| `tests/property/test_pii_redactor_properties.py` | 18 + 1 xfail | n/a (no clock) |
| `tests/property/test_correlator_scoring_properties.py` | 14 | Pattern A |
| `tests/property/test_audit_panel_heuristics_properties.py` | 16 | Pattern A |
| `tests/property/test_observability_aggregator_properties.py` | 14 | Pattern A |
| `tests/property/test_live_portfolio_sortino_properties.py` | 12 | Pattern A |
| `tests/property/test_walkforward_properties.py` (Lane 9 wiring) | ≥ 6 | Pattern A |

When you add a new property test that touches a clock primitive, follow this
ADR: inject the clock, do not let Hypothesis generate timestamps that
disagree with the impl's notion of "now". The
`tests/property/test_walkforward_properties.py` invariants are the reference
for combining Hypothesis strategies with deterministic clocks against the
walk-forward engine.
