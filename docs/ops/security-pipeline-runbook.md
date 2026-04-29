# Security Pipeline Runbook

Last reviewed: 2026-04-29

This runbook covers `services/security_pipeline/` and
`com.sapphire.security-pipeline`, the daily local security sweep that scans
Sapphire source for secret patterns, runs dependency vulnerability checks,
refreshes threat-intel summary data, writes a structured report, and publishes
a completion event.

The security pipeline is production-adjacent because real findings may trigger
operator notification. Manual operation should prefer tests, report inspection,
and fixture-backed checks. Do not run the full pipeline manually on the
canonical checkout unless a real alert is acceptable.

## Ownership

| Item | Path |
|---|---|
| Service | `services/security_pipeline/run.py` |
| LaunchAgent | `infra/launchagents/com.sapphire.security-pipeline.plist` |
| Unit tests | `tests/unit/test_services_security_pipeline.py` |
| Daily report | `data/security/YYYY-MM-DD/pipeline.json` |
| Stdout log | `data/logs/security-pipeline.log` |
| Stderr log | `data/logs/security-pipeline-err.log` |
| Routine pause name | `security-pipeline` |
| Event topic | `security.pipeline.completed` |

## Data Flow

```text
LaunchAgent at 03:00 local
  -> services/security_pipeline/run.py
  -> scan_secrets() over lib/, services/, plugins/
  -> scan_dependencies() via python -m pip_audit --format=json --desc
  -> refresh_threat_intel() via plugins/claw-sapphire/tools/threat_intel.py
  -> compute_score()
  -> data/security/YYYY-MM-DD/pipeline.json
  -> event bus topic security.pipeline.completed
  -> notify.py only when secrets exist or posture grade is D/F
```

The report is also part of the downstream data plane through
`lib/foundry/ingestion.py`, which treats `data/security/**/*.json` as an Alert
source. Do not claim a dashboard or SOC page is fresh from this pipeline until
that consumer path has been verified in the current checkout.

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.security-pipeline
```

Inspect recent logs:

```bash
tail -n 200 data/logs/security-pipeline.log
tail -n 200 data/logs/security-pipeline-err.log
```

Inspect the latest report without changing state:

```bash
latest_dir="$(ls -td data/security/* 2>/dev/null | head -1)"
test -n "$latest_dir" && python3 -m json.tool "$latest_dir/pipeline.json"
```

Expected report shape:

```json
{
  "date": "2026-04-29",
  "timestamp": "2026-04-29T03:00:00+00:00",
  "secrets": {"count": 0, "findings": []},
  "dependencies": {"python": [], "status": "ok"},
  "threats": {"count": 0},
  "posture": {"score": 100, "grade": "A"}
}
```

Run the safe local verification path:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_services_security_pipeline.py -q
```

This test suite exercises scoring, secret-pattern detection, pip-audit error
handling, threat-intel subprocess handling, report writes, event publishing,
and notification gating without spawning real external commands.

Run the full service only when a real notification is acceptable:

```bash
/usr/local/bin/python3 services/security_pipeline/run.py
```

The full run can call `plugins/claw-sapphire/tools/notify.py` when secrets are
found or the posture grade is `D`/`F`. That is correct for the scheduled daily
job, but it is not a harmless smoke test.

## Routine Pause

Pause before maintenance, before intentionally noisy test data is committed, or
when dependency tooling is returning known-bad output:

```bash
mkdir -p ~/.sapphire/routine_pause
date -u +%Y-%m-%dT%H:%M:%SZ > ~/.sapphire/routine_pause/security-pipeline
```

Resume after the fixture/unit checks are clean:

```bash
rm ~/.sapphire/routine_pause/security-pipeline
```

The service calls `abort_if_paused("security-pipeline")` before scanning or
loading downstream tooling, so a pause should stop the run before report writes,
event publishes, or notifications.

## Scoring Model

`compute_score()` starts at 100 and deducts:

| Signal | Deduction |
|---|---:|
| Secret finding | 10 each, capped at 40 |
| Vulnerable dependency | 5 each, capped at 30 |
| Threat-intel count | 2 each, capped at 20 |

Grades are:

| Grade | Score |
|---|---|
| A | 90-100 |
| B | 75-89 |
| C | 60-74 |
| D | 40-59 |
| F | 0-39 |

The minimum practical score from the current caps is 10. A low grade should be
treated as an operator signal, not as a deploy gate by itself, until the
underlying findings have been reviewed.

## Common Failures

### LaunchAgent Loaded Idle

`loaded idle (last_status=0)` is normal between 03:00 daily runs. Check the
latest `data/security/YYYY-MM-DD/pipeline.json` timestamp before treating idle
as stale.

### No Report for Today

1. Check whether the routine pause flag exists.
2. Check launchd state and stderr.
3. Confirm the canonical checkout path in the plist still points at
   `/Users/aribs/Code/Sapphire`.
4. Run the unit test suite before considering a manual full run.

### pip-audit Missing or Broken

`scan_dependencies()` records `pip-audit not installed` or `error: ...` in the
report and continues. This keeps the LaunchAgent from restart-looping, but it
means the dependency section is incomplete. Install or repair `pip-audit`, then
rerun the unit tests and wait for the next scheduled cycle or run manually only
if notification behavior is understood.

### Secret Findings Look Like False Positives

Do not paste the preview into chat or issues until it is redacted. Open the
listed file locally, determine whether the match is a real secret, generated
fixture, or overly broad regex hit, and fix the source or detector in a PR. Keep
test fixtures under the unit suite rather than committing real-looking tokens
to production paths.

### Threat Intel Tool Fails

`refresh_threat_intel()` reports `tool not found`, `empty response`, or
`error: ...` and the pipeline continues with a threat count of zero. Check
`plugins/claw-sapphire/tools/threat_intel.py` and the
`threat-intel-sweep-runbook.md` before changing the security pipeline. The
cloud routine and this local LaunchAgent are related, but they are not the same
surface.

### Notification Did Not Fire

Notification is only expected when at least one secret finding exists or the
posture grade is `D`/`F`. Passing grades with zero secrets should not call
`notify.py`. Verify with `tests/unit/test_services_security_pipeline.py` before
changing alert conditions.

### Notification Fired Unexpectedly

Pause the routine, save the latest report and last 200 log lines, then inspect
the `secrets.count`, dependency finding count, and threat count. Do not disable
`notify.py` globally. Fix the noisy detector, dependency source, or threat
input, then resume the routine after tests are green.

## Recovery

If a run produced a bad report, preserve it before rerunning:

```bash
bad_dir="data/security/$(date -u +%Y-%m-%d)"
test -d "$bad_dir" && cp "$bad_dir/pipeline.json" \
  "$bad_dir/pipeline.json.$(date -u +%Y%m%dT%H%M%SZ).bak"
```

If logs are noisy, rotate by copying rather than deleting:

```bash
cp data/logs/security-pipeline.log \
  data/logs/security-pipeline.log.$(date -u +%Y%m%dT%H%M%SZ).bak
cp data/logs/security-pipeline-err.log \
  data/logs/security-pipeline-err.log.$(date -u +%Y%m%dT%H%M%SZ).bak
```

Then use the safe verification path:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_services_security_pipeline.py -q
```

Only after the test suite is green should the operator resume the routine or
allow the next scheduled launchd fire.

## Safety Notes

- Do not use the full service command as a casual smoke test; it can send real
  operator notifications on real findings.
- Do not weaken secret regexes to hide a noisy result without adding a
  regression test.
- Do not print secret values, notification payload credentials, or raw
  `notify.py` configuration.
- Do not treat `pip-audit not installed` as a clean dependency report.
- Do not open live threat-intel issues from this runbook; use
  `threat-intel-sweep-runbook.md` for the cloud routine and issue workflow.
- Do not delete historical `data/security/` reports unless the operator asks
  for destructive retention cleanup.

## Escalation

Escalate when:

- A real secret finding appears in tracked source.
- The pipeline sends or would send a notification for a false-positive finding.
- Dependency scanning is unavailable for more than one daily cycle.
- The report is missing or malformed after launchd reports a successful run.
- Event publishing fails repeatedly and downstream Foundry/SOC consumers depend
  on the alert stream.

Include the latest report path, posture grade, counts by category, last 200
stdout/stderr lines, launchd status, and whether the routine pause flag was
present. Redact all secret previews before pasting evidence into issues or PRs.
