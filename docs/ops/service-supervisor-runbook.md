# Service Supervisor Runbook

Last reviewed: 2026-04-30

## Triage Quickstart

Failure mode addressed: a monitored LaunchAgent is repeatedly unloading and
the supervisor is either failing to recover it OR has hit its hourly restart
cap.

```bash
launchctl list com.sapphire.service-supervisor
```

```bash
PYTHONPATH=/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools \
  /usr/local/bin/python3 -m service_supervisor --dry-run
```

```bash
tail -n 200 ~/Library/Logs/sapphire-service-supervisor.log
```

The dry-run is read-only: it reports what the supervisor WOULD do without
making any changes. If `skipped_cooldown` is populated, a label has hit the
hourly restart cap — the supervisor is intentionally backing off, not broken.
For underlying daemon failures, escalate to the failing label's runbook
rather than retargeting the supervisor.

Live monitors: Telegram PM bot `/svc status` command (the same dry-run
output); dashboard `/observability` supervisor tile.
On-call escalation: ops owner; p3 unless multiple monitored labels are
flapping simultaneously, then p2.

This runbook covers `com.sapphire.service-supervisor`, the one-shot local
LaunchAgent that checks selected Sapphire LaunchAgents every minute and attempts
bounded self-healing when a monitored job is unloaded or crashed.

The supervisor is intentionally conservative: it has per-label cooldowns, a
rolling hourly restart cap, persistent state, and a dry-run mode used by the
Telegram PM bot's `/svc status` command. It must remain a recovery helper, not a
general remote shell.

## Ownership

| Item | Path |
|---|---|
| Service-local plist | `services/service_supervisor/launchagent/com.sapphire.service-supervisor.plist` |
| One-shot wrapper | `services/service_supervisor/run_once.sh` |
| Supervisor module | `plugins/claw-sapphire/tools/service_supervisor.py` |
| LaunchAgent status source | `plugins/claw-sapphire/tools/dev_pulse.py` |
| Persistent state | `~/Library/Application Support/sapphire/service_supervisor/state.json` |
| Log file | `~/Library/Logs/sapphire-service-supervisor.log` |
| Routine pause name | `service-supervisor` |

## Monitored Labels

The supervisor accepts only labels from
`plugins/claw-sapphire/tools/dev_pulse.py::DEFAULT_LAUNCHAGENT_LABELS` and
ignores `com.sapphire.service-supervisor` itself to avoid recursive restarts.

Current monitored labels include dashboard, inference proxy, signal logger,
OpenBB API, control-plane, PM bot, logrotate, regional-intel, and Hermes
gateway. If a new LaunchAgent should be supervised, add it to that list in a
separate code PR with tests.

## Normal Operation

Check that launchd is scheduling the one-shot job:

```bash
launchctl list com.sapphire.service-supervisor
```

Run a dry-run preview from the repo root:

```bash
PYTHONPATH=/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools \
  /usr/local/bin/python3 -m service_supervisor --dry-run
```

Inspect logs:

```bash
tail -n 200 ~/Library/Logs/sapphire-service-supervisor.log
```

Inspect persistent state:

```bash
python3 -m json.tool "$HOME/Library/Application Support/sapphire/service_supervisor/state.json"
```

The dry-run summary has:

```json
{
  "ok": true,
  "attempted": [],
  "recovered": [],
  "failed": [],
  "skipped_cooldown": [],
  "errors": []
}
```

## Restart Rules

The supervisor can take two recovery actions:

| Reason | Action |
|---|---|
| `unloaded_when_expected` | `launchctl bootstrap gui/<uid> ~/Library/LaunchAgents/<label>.plist` |
| `crashed` | `launchctl kickstart -k gui/<uid>/<label>` |

It will skip instead of restart when:

- The per-label restart cooldown has not elapsed.
- The label has already failed twice consecutively.
- The rolling hourly restart cap has been reached.
- The requested label is not on the allowlist.
- The `service-supervisor` routine is paused.

## Common Failures

### Dry-Run Shows a Restart Would Happen

1. Read the `attempted` item and identify the label plus reason.
2. Check the owning service runbook and logs.
3. If the label is healthy after manual inspection, no action is required; the
   next supervisor run should clear consecutive failures.
4. If the label is actually down, let the scheduled supervisor attempt recovery
   or run a single non-dry-run invocation locally:

   ```bash
   PYTHONPATH=/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools \
     /usr/local/bin/python3 -m service_supervisor --label com.sapphire.dashboard
   ```

### Restart Cap Hit

The summary includes `rate_limited: max restart attempts per rolling hour
reached`. Do not raise the cap reflexively. A restart storm usually means the
child service cannot boot. Read that service's stderr, fix the root cause, and
only then clear stale state if needed.

### State File Is Corrupted

The supervisor tolerates unreadable JSON by starting with empty state. If manual
repair is needed, move the file aside instead of deleting it:

```bash
mv "$HOME/Library/Application Support/sapphire/service_supervisor/state.json" \
   "$HOME/Library/Application Support/sapphire/service_supervisor/state.json.$(date +%Y%m%dT%H%M%S).bak"
```

## Safety Notes

- Do not add arbitrary labels. The allowlist is the safety boundary.
- Do not supervise trading execution toggles or external mutation jobs without
  a dedicated design review.
- Do not expose the non-dry-run command through Telegram. `/svc status` must
  stay dry-run.
- Do not disable cooldowns except in a local, operator-attended recovery.

## Escalation

Escalate when:

- The same label appears in `failed` twice in a row.
- The hourly restart cap is hit.
- Firestore activity writes fail and the operator needs the activity trail.
- A supervised label repeatedly exits cleanly but never stays running.

Include the dry-run JSON, last 200 supervisor log lines, `launchctl list
<label>`, and the owning service log excerpt.
