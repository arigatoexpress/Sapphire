# Self-Optimization Runbook

Last reviewed: 2026-04-29

This runbook covers `com.sapphire.self-optimization`, the weekly local
LaunchAgent that reviews closed signal outcomes and adjusts signal-enhancer
weights when there is enough decisive evidence.

The self-optimization loop is conservative, but it is not read-only. A normal
run can write `data/enhancer_weights.json`, append `data/system_events.jsonl`,
and publish `optimization.completed` to the event bus. Treat it as an
operator-reviewed tuning surface, not as autonomous trade approval.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.self-optimization.plist` |
| Optimizer script | `services/intelligence/optimize.py` |
| Signal outcomes | `data/signals/YYYY-MM-DD.jsonl` |
| Weight output | `data/enhancer_weights.json` |
| Event log | `data/system_events.jsonl` |
| Event topic | `optimization.completed` |
| Stdout log | `/Users/aribs/Library/Logs/sapphire/self-optimization.log` |
| Stderr log | `/Users/aribs/Library/Logs/sapphire/self-optimization.err` |
| Routine pause name | `self-optimization` |

## Schedule

The LaunchAgent runs Sunday at 23:00 local:

```bash
/usr/local/bin/python3 /Users/aribs/Code/Sapphire/services/intelligence/optimize.py
```

`RunAtLoad=false` and `ThrottleInterval=3600`.

## Data Flow

```text
LaunchAgent Sunday 23:00
  -> services/intelligence/optimize.py
  -> read data/signals/YYYY-MM-DD.jsonl for last 30 days
  -> compute feature importance over win/loss/break_even outcomes
  -> if decisive trades >= 10, damped adjustment of enhancer weights
  -> data/enhancer_weights.json when changes are applied
  -> optimization.completed event bus publish
  -> data/system_events.jsonl append
```

The optimizer currently adjusts `regime_penalty` and `regime_boost` only. It
uses safe bounds and a 0.25 learning rate so one noisy week cannot fully rewrite
the enhancer.

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.self-optimization
launchctl print gui/$(id -u)/com.sapphire.self-optimization
```

Inspect logs:

```bash
tail -n 200 /Users/aribs/Library/Logs/sapphire/self-optimization.log
tail -n 200 /Users/aribs/Library/Logs/sapphire/self-optimization.err
```

Inspect current weights:

```bash
test -f data/enhancer_weights.json && python3 -m json.tool data/enhancer_weights.json
```

Inspect recent optimization events:

```bash
rg -n '"optimization.completed"|self-optimization' data/system_events.jsonl | tail -n 10
```

Run a dry-run only when an event append is acceptable:

```bash
/usr/local/bin/python3 services/intelligence/optimize.py --dry-run
```

`--dry-run` prevents weight persistence, but it still publishes/appends the
optimization report. It is not a strict no-write command.

## Strict Read-Only Inspection

For strict read-only work, inspect files and logs only:

```bash
ls -lt data/signals/*.jsonl | head
test -f data/enhancer_weights.json && python3 -m json.tool data/enhancer_weights.json
tail -n 50 /Users/aribs/Library/Logs/sapphire/self-optimization.log
```

Do not `launchctl kickstart` during inspection; that is a real optimization
cycle and can write data.

## Routine Pause

Pause before signal schema changes, enhancer logic changes, or incident review:

```bash
mkdir -p ~/.sapphire/routine_pause
date -u +%Y-%m-%dT%H:%M:%SZ > ~/.sapphire/routine_pause/self-optimization
```

Resume after the signal files and optimizer behavior are understood:

```bash
rm ~/.sapphire/routine_pause/self-optimization
```

The script calls `abort_if_paused("self-optimization")` before running.

## Common Failures

### Skipped for Insufficient Samples

The optimizer requires at least 10 decisive win/loss trades. If it logs a skip,
check whether `data/signals/` contains recent scored outcomes and whether the
outcome values are one of `win`, `loss`, or `break_even`.

### Weights Changed Unexpectedly

Pause the routine, copy `data/enhancer_weights.json`, and inspect the latest
`optimization.completed` row in `data/system_events.jsonl`. The report includes
old weights, new weights, changes, decisive trade count, and notes. Revert the
weights file through a normal PR or a preserved local backup; do not hand-edit
while the routine is still enabled.

### Event Publish Fails

The script catches event-bus failures and still appends the legacy JSONL audit
row when possible. If both event bus and JSONL append fail, save stderr and
check filesystem permissions under `data/`.

### Signal Schema Drift

The optimizer expects fields such as `outcome`, `regime`, `funding_flag`,
`kronos_direction`, `confidence`, and `enhancer_flags`. Unknown or missing
fields reduce evidence quality. Fix producers or add fixture-backed optimizer
tests before changing the weighting math.

### Bad Recommendation

The safe response is to pause, preserve the report, revert or replace
`data/enhancer_weights.json`, and add a regression fixture. Do not widen bounds
or raise the learning rate as an immediate reaction.

## Safety Notes

- Do not connect optimizer output directly to live trading.
- Do not change `MIN_SAMPLES`, learning rate, or bounds without tests and a
  rollback note.
- Do not run kickstart as a harmless smoke test.
- Do not delete `data/signals/` or `data/system_events.jsonl`.
- Do not paste raw signal records into issues if they include sensitive source
  context.
- Do not treat a positive optimizer report as permission to enable execution.

## Escalation

Escalate when:

- Weights change in a way that materially alters signal confidence.
- The optimizer applies a change from too few or malformed samples.
- Event/audit logging fails for an optimization run.
- Signal outcome data appears corrupted or duplicated.
- Any downstream code attempts to turn self-optimization into live-order
  authorization.

Include launchd status, latest weight file, latest optimization event with
sensitive fields redacted, decisive trade count, notes, and last 200 log lines.
