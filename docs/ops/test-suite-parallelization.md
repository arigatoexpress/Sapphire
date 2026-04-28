# Test Suite Parallelization

**Last updated:** 2026-04-27
**Owner:** Ari (commander) · maintained alongside `pyproject.toml` test config

## Why this exists

Sapphire's `tests/unit/` collection has crossed 3,500 tests and the serial wall
time on a single Mac core was approaching 80 seconds. CI minutes are billed
per-second on every PR so a 2× wall-time reduction directly cuts the cost of
the green-bar gate. This document explains how parallelization is configured,
which test files are pinned to a single worker, and how to verify the soak
posture stays clean.

## What is parallelized

### Project-level

`pytest-xdist >= 3.6` is declared as a dev/test dependency in `pyproject.toml`.
Running

```bash
python3 -m pytest tests/unit/ -n auto
```

distributes tests across workers (default: `--dist=load`, one test per worker
slot) using one process per CPU core. Anyone wanting to parallelize the
existing CI workflow only needs to add `-n auto` to the existing pytest
invocation — no further config required.

### Per-file (the original justification)

The largest single test file is
`tests/unit/test_prediction_markets.py` — 2,451 lines, 225 tests covering the
prediction-market intelligence pipeline (Polymarket + Kalshi clients, the
aggregator, arbitrage detector, accuracy tracker, whale-activity heuristics,
volume-history tracking, Telegram command handlers, and the swarm/PM
integration layer).

The prediction_markets test module is `xdist`-safe by construction:

- Every `os.environ` mutation is wrapped in `patch.dict`, scope-limited.
- No module-level filesystem writes (we grep for `open(`, `write_text`,
  `Path(...).write` — none).
- No `time.sleep` based timing.
- No process-level singletons whose state leaks between tests.

So `pytest -n auto tests/unit/test_prediction_markets.py` Just Works without
any `xdist_group` annotations.

## What is NOT parallelized

The following constructs serialize naturally and don't need workers:

| Pattern | Why it's serial-friendly |
|---|---|
| `monkeypatch.setattr` mutations | `monkeypatch` is fixture-scoped — xdist gets a fresh fixture per test |
| `tmp_path` fixtures | Each test gets its own directory under `pytest`'s tmp tree |
| In-process module-level singletons (e.g. the x402 default middleware) | Each xdist worker has its own Python interpreter and its own module table |

The handful of tests that mutate process-global state without a context
manager (these are rare and audited at PR time) get an `xdist_group("group")`
marker that pins them to the same worker. The marker is registered in
`pyproject.toml` `[tool.pytest.ini_options].markers` so `--strict-markers`
doesn't reject it. As of 2026-04-27 no test in the repo carries this marker
yet — it's available for future use.

## Per-test annotations

To pin a group of tests to one worker, add:

```python
@pytest.mark.xdist_group("trading-engine")
def test_my_serializable_thing():
    ...
```

Tests sharing the same group string land on the same worker. Use this when
two tests must run sequentially because they share a real-world resource
(e.g. a port, a temp-file lock, a process the test spawns). When in doubt,
prefer `tmp_path` or `monkeypatch` over xdist groups; `xdist_group` is a
last-resort tool, not the default.

## Measured timings

Hardware: M-series Mac, 14 logical cores, Python 3.14.3, pytest 9.0.3,
pytest-xdist 3.8.0. All runs after the first warmup. Variance is ±15% so
trends matter, not individual numbers.

### Whole `tests/unit/` collection (3,526 tests)

| Mode | Wall time | Speedup |
|---|---|---|
| serial (`pytest tests/unit/`) | 77.57 s | baseline |
| parallel (`pytest tests/unit/ -n auto`) | 39.50 s | **1.96×** |

This is where xdist earns its keep: the long tail of file-level imports + the
~30 mid-weight test files all parallelize cleanly.

### Single file `test_prediction_markets.py` (225 tests)

| Mode | Wall time | Speedup |
|---|---|---|
| serial (`pytest test_prediction_markets.py`) | 0.21 s | baseline |
| `-n 2` | 1.35 s | 0.16× (slower) |
| `-n 4` | 1.47 s | 0.14× (slower) |
| `-n 8` | 1.80 s | 0.12× (slower) |
| `-n auto` (14 workers) | 1.91 s | 0.11× (slower) |

For a single fast file, worker spawn cost (~150–200 ms per worker) dominates
the 200 ms of actual test work. **Don't run a single small file with `-n
auto`.** Run a single file serial; reach for `-n auto` when running the
*whole* `tests/unit/` collection. CI does the latter.

### Distribution strategy comparison

`--dist=load` (the default) wins for prediction_markets:

| Strategy | Wall time |
|---|---|
| `--dist=load` (4 workers) | 1.46 s |
| `--dist=loadfile` (4 workers) | 1.59 s |
| `--dist=loadscope` (4 workers) | 1.57 s |

Any module-level setup cost (the alpha service `sys.path` shim, redis-py's
fallback warning) is paid once per worker; spreading by file or scope adds no
benefit when there's only one file.

## Soak posture

The test-suite parallelization is opt-in (`-n auto` flag), so the default
`pytest tests/unit/` invocation behaves exactly as before. CI workflows
upstream of this repo (`.github/workflows/ci.yml`) are unchanged by this
tranche — they continue to run serial. If a future tranche flips CI to
parallel, the recommended sequence is:

1. Add `-n auto` to `.github/workflows/ci.yml` for the unit suite only.
2. Run for 1 week of business-hour PR traffic.
3. Watch for any test that fails *only* under parallel — these are usually
   process-global-state leaks, addressable by `xdist_group` or by
   refactoring to use `monkeypatch`.
4. If clean for 7 days, parallelization is safe to depend on.

The plugin suite under `plugins/claw-sapphire/tests/` is small (~117 tests,
<5 s serial) and not worth parallelizing — listed here so future contributors
don't waste time on it.

## What this does NOT change

- The trading critical path (signal logger, paper trader, kill switch) has its
  own serial suite under `tests/integration/` (where present) — those stay
  serial because they bind real ports.
- LaunchAgent-driven services (foundry sync, content engine, security scanner)
  have their own end-to-end tests that are intentionally not parallelized;
  they exercise filesystem and subprocess paths that need ownership clarity.
- The CI gate (gitleaks, bandit, ruff, registry validator) is unaffected —
  these are fast and run before pytest.

## Verifying locally

```bash
# Confirm xdist is installed
python3 -m pytest --version  # should mention pytest-xdist

# Serial baseline
time python3 -m pytest tests/unit/ --tb=no -q

# Parallel run
time python3 -m pytest tests/unit/ -n auto --tb=no -q

# Single hot file (NOT parallel — see above)
python3 -m pytest tests/unit/test_prediction_markets.py -q
```

If the parallel run hangs or errors with `INTERNALERROR>`, that's a sign a
test is leaking process-global state. Bisect with `-n 2`, then `-n 1` to
find the offender, then either pin it with `xdist_group` or refactor the
shared state out.
