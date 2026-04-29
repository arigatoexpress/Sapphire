# Morning Digest Runbook

Last reviewed: 2026-04-29

This runbook covers `com.sapphire.morning-digest`, the service-local LaunchAgent
for the cross-repo Sapphire morning operational digest. It reads repo, CI, Cloud
Run, launchctl, and paper-trading state through `dev_pulse`, then sends an
informational p3 Telegram digest. It is separate from `com.sapphire.morning-brief`.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `services/morning_digest/launchagent/com.sapphire.morning-digest.plist` |
| Wrapper | `services/morning_digest/run_once.sh` |
| Tool module | `plugins/claw-sapphire/tools/morning_digest.py` |
| Pulse module | `plugins/claw-sapphire/tools/dev_pulse.py` |
| Telegram helper | `plugins/claw-sapphire/tools/notify.py` |
| Log file | `/Users/aribs/Library/Logs/sapphire-morning-digest.log` |
| Pause flag | `/Users/aribs/.sapphire/routine_pause/morning-digest` |

## Schedule

The plist runs daily at 08:00 local:

```bash
/bin/zsh /Users/aribs/Code/Sapphire/services/morning_digest/run_once.sh
```

The wrapper changes to the repo root, sets
`PYTHONPATH=/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools`, and execs:

```bash
/usr/local/bin/python3 -m morning_digest
```

## Data Flow

```text
launchd daily 08:00 local
  -> services/morning_digest/run_once.sh
  -> python3 -m morning_digest
  -> abort_if_paused("morning-digest")
  -> dev_pulse.pulse()
  -> format_morning_digest_markdown()
  -> notify.send_alert(..., priority="p3")
```

Inputs include GitHub PR/CI state, local repo dirt, Cloud Run service health,
launchctl status, paper-trading files, signal JSONL files, and optional Firestore
activity data for partner webhook delivery. Each source should degrade rather
than block the whole digest.

## Normal Operation

Validate plist syntax and state:

```bash
plutil -lint services/morning_digest/launchagent/com.sapphire.morning-digest.plist
launchctl print gui/$(id -u)/com.sapphire.morning-digest
```

Inspect output:

```bash
tail -n 120 /Users/aribs/Library/Logs/sapphire-morning-digest.log
```

Run the no-send path:

```bash
services/morning_digest/run_once.sh --dry-run
```

The dry-run returns JSON, includes the rendered message, and does not send
Telegram. It can still call local CLIs and optional external read APIs such as
`gh`, `gcloud`, and Firestore.

Run focused tests:

```bash
PYTHONPATH=plugins/claw-sapphire/tools /usr/local/bin/python3 -m pytest \
  plugins/claw-sapphire/tests/test_morning_digest.py \
  plugins/claw-sapphire/tests/test_dev_pulse.py \
  plugins/claw-sapphire/tests/test_sapphire_pm_bot.py::test_digest_morning_reads_archive_when_present \
  plugins/claw-sapphire/tests/test_sapphire_pm_bot.py::test_digest_morning_explains_when_missing -q
```

## Known Gap: Digest Archive

The PM bot `/digest morning` path expects
`data/morning_digest/YYYY-MM-DD.md` when an archive exists. Current
`morning_digest.py` does not implement an `--archive` flag or write that file.
Do not claim `/digest morning` is backed by a fresh archive until that code path
lands. Today, the scheduled digest is a send path, while the archive read is a
future integration gap.

## Common Failures

### LaunchAgent Not Loaded

The service-local plist may be valid but not loaded in the current GUI session.
That means no scheduled digest will fire even if manual dry-run works.

### Missing Telegram Secret

`notify.py` returns explicit missing token/chat errors. Do not print secret file
contents. Check only presence and path.

### Optional Tool Missing

`dev_pulse` calls `gh`, `gcloud`, local git, launchctl, and optional Firestore
helpers. Missing or slow tools should appear as degraded sections in the digest.

### Dry-Run Looks Slow

This is expected when external read-only status commands are slow. The digest has
timeouts, but a full pulse can still take longer than a simple unit test.

### Pause Flag

`abort_if_paused("morning-digest")` exits cleanly when the pause flag exists.
Last exit code 0 can mean skipped.

## Recovery

Use this order:

1. Validate plist syntax.
2. Check whether launchd has the service loaded.
3. Tail `/Users/aribs/Library/Logs/sapphire-morning-digest.log`.
4. Run `services/morning_digest/run_once.sh --dry-run`.
5. If only `/digest morning` is broken, inspect the archive gap before changing
   the scheduled send path.

## Safety Notes

- Do not run non-dry-run `morning_digest` manually unless Ari explicitly wants a
  real Telegram digest sent.
- Do not send test Telegram messages from a runbook lane.
- Do not expose Telegram token, chat ID, Firestore credentials, or `.env`
  contents.
- Do not wire digest output into trading actions.
- Do not bootstrap, unload, kickstart, or retarget the LaunchAgent while
  performing read-only inspection.

## Escalation

Escalate when:

- The digest did not fire and launchd was expected to load it.
- Non-dry-run sends return repeated Telegram errors.
- Dry-run fails before producing a JSON response.
- `/digest morning` is expected operationally but no archive writer exists.
- The digest reports materially wrong cross-repo or paper-trading state.

Include plist state, log tail, dry-run JSON summary, degraded source list, and
whether the archive path exists. Redact secrets and avoid live-send tests unless
explicitly approved.
