# Backtest Weekly Runbook

Last reviewed: 2026-04-30

## Triage Quickstart

Failure mode addressed: the weekly sweep did not produce a fresh
`strategy_sweep_*.json` artifact, or the dashboard `/api/backtest-results`
endpoint reports stale rankings.

```bash
launchctl print gui/$(id -u)/com.sapphire.backtest-weekly
```

```bash
ls -lt data/backtests/strategies/strategy_sweep_*.json | head
```

```bash
tail -n 200 /Users/aribs/Library/Logs/sapphire/backtest-weekly.err
```

If no artifact newer than the last Saturday 22:00 exists, the sweep did not
run. Check the pause flag at `/Users/aribs/.sapphire/routine_pause/backtest-weekly`,
then stderr for yfinance failures (the most common cause is rate-limit or
symbol-resolution drift).

Live monitors: dashboard `/performance` and `/api/backtest-results`; remote
workflow `.github/workflows/weekly-backtest.yml`.
On-call escalation: analytics owner; p3 unless two consecutive Saturdays are
missed, then p2. Do not treat sweep output as trade authorization — strategy
selection still flows through paper trading and operator review.

This runbook covers `com.sapphire.backtest-weekly`, the local weekly
LaunchAgent that runs the Sapphire strategy sweep and writes ranked backtest
artifacts under `data/backtests/strategies/`.

The job is research and artifact generation only. It does not execute trades,
place orders, send Telegram messages, or publish strategy recommendations. Treat
the output as analytical evidence that still requires operator review.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.backtest-weekly.plist` |
| Sweep runner | `lib/analytics/run_strategies.py` |
| Strategy engine | `lib/analytics/strategies.py` |
| Backtest engine | `lib/analytics/backtest_engine.py` |
| Remote workflow | `.github/workflows/weekly-backtest.yml` |
| Remote soak note | `docs/org/backtest-weekly-shadow-soak-2026-04-26.md` |
| Artifact comparator | `scripts/ops/compare_backtest_artifacts.py` |
| Unit tests | `tests/unit/test_backtest_signature.py`, `tests/unit/test_remote_routine_workflows.py` |
| Output directory | `data/backtests/strategies/` |
| Stdout log | `/Users/aribs/Library/Logs/sapphire/backtest-weekly.log` |
| Stderr log | `/Users/aribs/Library/Logs/sapphire/backtest-weekly.err` |
| Installed plist | `/Users/aribs/Library/LaunchAgents/com.sapphire.backtest-weekly.plist` |
| Routine pause name | `backtest-weekly` |

## Schedule

The LaunchAgent runs Saturday at 22:00 local, after markets close and before
Sunday review:

```bash
/usr/local/bin/python3 -m lib.analytics.run_strategies --days 90 --bankroll 10000
```

`RunAtLoad=false`, so loading the plist does not immediately start a sweep.
The installed plist should match the versioned plist; edit the repo copy first
and then reinstall, not the other way around.

## Data Flow

```text
LaunchAgent Saturday 22:00
  -> lib.analytics.run_strategies
  -> yfinance OHLCV fetch for BTC-USD, ETH-USD, SOL-USD, SPY
  -> strategy grid sweep over Sapphire strategies
  -> data/backtests/strategies/strategy_sweep_*.json
  -> data/backtests/strategies/best_per_symbol_*.json
  -> optional remote-shadow comparison via compare_backtest_artifacts.py
```

Current default sweep shape is 90 days, bankroll 10000, four symbols, and the
configured strategy/parameter grid. The generated JSON contains metadata with
git SHA, workflow run ID when present, yfinance version, config, and bar
fingerprints.

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.backtest-weekly
launchctl print gui/$(id -u)/com.sapphire.backtest-weekly
```

Inspect logs:

```bash
tail -n 200 /Users/aribs/Library/Logs/sapphire/backtest-weekly.log
tail -n 200 /Users/aribs/Library/Logs/sapphire/backtest-weekly.err
```

Find the latest artifacts:

```bash
ls -lt data/backtests/strategies/strategy_sweep_*.json | head
ls -lt data/backtests/strategies/best_per_symbol_*.json | head
```

Inspect artifact metadata without rerunning the sweep:

```bash
/usr/local/bin/python3 - <<'PY'
import json
from pathlib import Path
latest = max(Path("data/backtests/strategies").glob("strategy_sweep_*.json"))
data = json.loads(latest.read_text())
print(latest)
print(json.dumps(data.get("metadata", {}), indent=2, sort_keys=True))
print("rows", len(data.get("results", [])))
PY
```

Run the safe test path:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_backtest_signature.py \
  tests/unit/test_remote_routine_workflows.py -q
```

The unit tests use synthetic bars and pinned workflow assertions. They do not
fetch live market data or regenerate canonical artifacts.

## Manual Sweep

Use a noncanonical output directory for manual smoke tests:

```bash
/usr/local/bin/python3 -m lib.analytics.run_strategies \
  --days 7 \
  --bankroll 10000 \
  --output-dir /tmp/sapphire-backtest-smoke
```

Use the canonical weekly command only when you intend to update
`data/backtests/strategies/`:

```bash
/usr/local/bin/python3 -m lib.analytics.run_strategies --days 90 --bankroll 10000
```

Do not commit generated data unless the PR is explicitly about refreshing
backtest artifacts.

Do not `launchctl kickstart` the weekly job during inspection. A kickstart is a
real sweep fire and can write canonical artifacts unless the command is first
changed to use a noncanonical output directory.

## Remote Shadow

The remote workflow runs `python -m lib.analytics.run_strategies --days 90
--bankroll 10000`, uploads `data/backtests/strategies/*.json`, and requires
only `contents: read`. The current soak gate lives in
`docs/org/backtest-weekly-shadow-soak-2026-04-26.md`.

Compare local and remote artifacts:

```bash
/usr/local/bin/python3 scripts/ops/compare_backtest_artifacts.py \
  --local-root data/backtests/strategies \
  --remote-root /path/to/weekly-backtest-artifact \
  --max-skew-minutes 90
```

Do not retire the local LaunchAgent until the soak note's scheduled-cycle gate
is satisfied and a separate PR records rollback.

## Routine Pause

Pause before data-source incidents, strategy-grid refactors, or artifact
cleanup:

```bash
mkdir -p ~/.sapphire/routine_pause
date -u +%Y-%m-%dT%H:%M:%SZ > ~/.sapphire/routine_pause/backtest-weekly
```

Resume after tests and artifact checks are clean:

```bash
rm ~/.sapphire/routine_pause/backtest-weekly
```

`run_strategies.py` calls `abort_if_paused("backtest-weekly")` before the sweep.

## Common Failures

### No Artifacts Written

Check stderr first, then confirm yfinance loaded bars for at least one symbol.
If all bar loads fail, the runner returns no results. Use the synthetic unit
tests to separate network/data-source issues from engine regressions.

### Unexpected Row Count

The comparator and soak note currently expect 756 rows for the default
90-day/four-symbol sweep shape. If strategy count, symbol list, parameter grid,
or composite thresholds changed intentionally, update tests, docs, and soak
expectations in the same PR.

### Metadata Missing or Stale

`strategy_sweep_*.json` and `best_per_symbol_*.json` should include metadata
with source, config, and bar fingerprints. Missing metadata breaks remote
shadow explainability. Run `tests/unit/test_backtest_signature.py` before
touching comparator thresholds.

### Remote/Local Comparison Warns

Small timestamp skew can be normal when local and remote sweeps run at different
times. Missing rows, leaderboard drift, or changed bar fingerprints need review.
Do not promote remote-shadow cutover on WARN/FAIL evidence that has not been
classified.

### Canonical Data Dirty After a Smoke

Manual smoke tests should use `--output-dir /tmp/...`. If canonical
`data/backtests/strategies/` changed accidentally, preserve the diff for review
before deciding whether to revert, stash, or commit. Do not delete artifacts
blindly.

## Safety Notes

- Do not connect backtest output directly to live execution.
- Do not change bankroll, symbols, or strategy grids in the LaunchAgent without
  tests and audit-note updates.
- Do not point the plist at `/Users/aribs/Code/_worktrees/*`.
- Do not upload or publish generated artifacts unless the target workflow or PR
  calls for it.
- Do not disable the local LaunchAgent until remote-shadow soak criteria and
  rollback notes are complete.
- Do not treat strong Sortino or return rows as trade approval.
- Do not delete historical files under `data/backtests/strategies/`.

## Escalation

Escalate when:

- The weekly sweep fails for more than one scheduled run.
- The default sweep row count changes unexpectedly.
- Remote shadow comparison reports missing rows or leaderboard drift.
- Generated artifacts would overwrite or replace diligence evidence.
- Any downstream system attempts to convert backtest output into live orders.

Include launchd status, command used, latest artifact paths, metadata summary,
row counts, comparator verdict when relevant, and last 200 stdout/stderr lines.
