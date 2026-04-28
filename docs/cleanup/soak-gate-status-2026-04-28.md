# Routine Soak Gate Status

Generated: 2026-04-28T03:46Z

Scope: read-only status report from `python3 scripts/ops/routine_soak_status.py
--format json`, GitHub Actions run metadata, and the existing soak evidence
docs. No workflows were dispatched, no LaunchAgents were changed, and no
Telegram messages were sent.

## Summary

All three routines are still in `collecting` state.

| Routine | Gate state | Latest comparison | Scheduled progress | Recommendation |
|---|---|---|---|---|
| `backtest-weekly` | collecting | PASS | 0/4 scheduled successes | Continue soak. Manual successes prove the path, but the weekly scheduled gate has not started accumulating yet. |
| `threat-refresh` | collecting | WARN, 0 FAIL rows | 3/24 scheduled successes, 10 scheduled total | Investigate scheduled failures/skips before cutover. Manual runs are not enough for the gate. |
| `content-engine` | collecting | WARN, 0 FAIL rows | 0/7 scheduled successes, 1 scheduled total | Continue soak and inspect the scheduled failure before relying on remote replacement. |

Production readiness sweep on the same live checkout reported `38 pass`, `8
warn`, `0 fail`, `2 skip`. The routine warnings are expected under
`--no-external`; they do not block this read-only report.

## Backtest Weekly

Current evidence:

- Remote workflow: `.github/workflows/weekly-backtest.yml`
- Comparator: `scripts/ops/compare_backtest_artifacts.py`
- Latest comparison: PASS
- Rows compared: 756
- Rows failed: 0
- Missing rows: 0 local, 0 remote
- Leaderboard top-3 order equal: true
- GitHub runs since soak start: 3 success, 2 failure, 1 cancelled
- Scheduled runs since soak start: 0

Read: the manual path is healthy, but the cutover gate explicitly requires
scheduled weekly cycles. Do not retire `com.sapphire.backtest-weekly` yet.

Next action:

- Wait for scheduled weekly cycles, or document why the schedule has not fired.

## Threat Refresh

Current evidence:

- Remote workflow: `.github/workflows/threat-refresh.yml`
- Comparator: `scripts/ops/compare_threat_artifacts.py`
- Latest comparison: WARN
- Rows compared: 15
- Rows pass: 10
- Rows warn: 5
- Rows fail: 0
- Missing rows: 0 local, 0 remote
- GitHub runs since soak start: 7 success, 6 failure, 2 skipped, 1 cancelled
- Scheduled runs since soak start: 10
- Scheduled successes since soak start: 3

Recent scheduled run outcomes:

| Created at UTC | Conclusion | Run |
|---|---|---|
| 2026-04-27T22:06:19Z | skipped | 25022102354 |
| 2026-04-27T18:19:20Z | skipped | 25012051128 |
| 2026-04-27T15:18:20Z | failure | 25003558299 |
| 2026-04-27T11:16:51Z | failure | 24991896158 |
| 2026-04-27T07:41:44Z | failure | 24982663056 |
| 2026-04-27T04:38:37Z | failure | 24976820200 |
| 2026-04-26T21:53:21Z | failure | 24967974681 |
| 2026-04-26T17:57:29Z | success | 24963262204 |
| 2026-04-26T14:09:25Z | success | 24958614115 |
| 2026-04-26T10:05:35Z | success | 24954006107 |

Read: the comparison quality is acceptable when artifacts exist, but scheduled
reliability is not cutover-ready. The next useful step is log taxonomy for the
scheduled failures and skipped runs, not a LaunchAgent cutover.

Next action:

- Pull logs for scheduled failure runs and classify failure kind in a follow-up
  PR. Keep the local LaunchAgent canonical.

## Content Engine

Current evidence:

- Remote workflow: `.github/workflows/content-engine.yml`
- Comparator: `scripts/ops/compare_content_artifacts.py`
- Latest comparison: WARN
- Rows compared: 4
- Rows pass: 0
- Rows warn: 4
- Rows fail: 0
- Missing rows: 0 local, 0 remote
- GitHub runs since soak start: 2 success, 2 failure, 2 cancelled
- Scheduled runs since soak start: 1
- Scheduled successes since soak start: 0

Run outcomes since soak start:

| Created at UTC | Event | Conclusion | Run |
|---|---|---|---|
| 2026-04-28T00:14:05Z | workflow_dispatch | success | 25026580176 |
| 2026-04-28T00:11:57Z | workflow_dispatch | cancelled | 25026513625 |
| 2026-04-28T00:04:21Z | workflow_dispatch | failure | 25026260386 |
| 2026-04-27T23:58:05Z | workflow_dispatch | cancelled | 25026048941 |
| 2026-04-27T13:27:46Z | schedule | failure | 24997830827 |
| 2026-04-26T20:39:21Z | workflow_dispatch | success | 24966520333 |

Read: the first comparator result is acceptable for shadow freshness drift, but
the scheduled gate has zero successes. Do not retire `com.sapphire.content-engine`.

Next action:

- Inspect scheduled run `24997830827` logs and update this report or the soak
  evidence doc with the failure class.

## Cutover Decision

None of the three routines is ready for local LaunchAgent retirement today.
Continue remote shadow collection and keep local runtime rollback trivial.
