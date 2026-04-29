# Logrotate Runbook

Last reviewed: 2026-04-29

This runbook covers `com.sapphire.logrotate`, the local LaunchAgent that
compresses oversized operator logs. It is a maintenance routine only: it never
reads secrets, never sends Telegram messages, and never touches trading state.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.logrotate.plist` |
| Script | `infra/logrotate.py` |
| Target log dir | `/Users/aribs/autonomy-status/logs/` |
| Target log dir | `/Users/aribs/.hermes/logs/` |
| Stdout log | `/Users/aribs/autonomy-status/logs/logrotate.log` |
| Stderr log | `/Users/aribs/autonomy-status/logs/logrotate.err` |
| Pause flag | `/Users/aribs/.sapphire/routine_pause/logrotate` |

## Schedule

The plist runs once daily at 03:30 local:

```bash
/usr/local/bin/python3 /Users/aribs/Code/Sapphire/infra/logrotate.py
```

`RunAtLoad=false`; there is no `KeepAlive`. A healthy launchd state is usually
"loaded, not running, last exit code 0" because the routine is a short batch job.

## Data Flow

```text
launchd at 03:30 local
  -> infra/logrotate.py
  -> abort_if_paused("logrotate")
  -> scan ~/autonomy-status/logs and ~/.hermes/logs
  -> gzip *.log and *.err files larger than 5 MB
  -> truncate the original file in place
  -> keep the 3 newest .gz archives per log stem
```

The script truncates, rather than deletes, active log files so already-running
processes can keep their file handles. More than three archives for the same log
stem are pruned by design.

## Normal Operation

Validate plist syntax:

```bash
plutil -lint \
  infra/launchagents/com.sapphire.logrotate.plist \
  ~/Library/LaunchAgents/com.sapphire.logrotate.plist
```

Inspect launchd state:

```bash
launchctl print gui/$(id -u)/com.sapphire.logrotate
```

Review recent output:

```bash
tail -n 80 /Users/aribs/autonomy-status/logs/logrotate.log
tail -n 40 /Users/aribs/autonomy-status/logs/logrotate.err
```

Check current and rotated log sizes:

```bash
find /Users/aribs/autonomy-status/logs /Users/aribs/.hermes/logs \
  -maxdepth 1 -type f \( -name '*.log' -o -name '*.err' -o -name '*.gz' \) \
  -exec ls -lh {} \;
```

A manual run is not read-only. It may compress, truncate, and prune logs:

```bash
/usr/local/bin/python3 infra/logrotate.py
```

Only run that manually when rotation is desired and preserving current log bytes
has already been considered.

## Common Failures

### Looks Idle But Is Healthy

Because this is a calendar job, launchd normally reports no active PID. Check
the last exit status and log timestamps instead of expecting a long-running
process.

### No Rotation Happened

Files below 5 MB are intentionally skipped. Confirm sizes before treating a
no-op as failure.

### Missing Log Directory

The script silently skips missing target directories. If no logs rotate and the
routine is otherwise healthy, verify both target directories exist and are owned
by the operator user.

### Permission Failure

Compression, truncation, and archive pruning require write access to the target
directory and files. Permission failures should appear in stderr. Preserve the
stderr tail and fix ownership; do not mass-delete logs.

### Paused Routine

`abort_if_paused("logrotate")` exits cleanly when the pause flag exists. A last
exit code of 0 can mean "skipped by pause", so inspect output before assuming a
rotation cycle completed.

## Recovery

If the installed plist drifts from the repo plist, preserve both copies before
changing anything:

```bash
cmp -s infra/launchagents/com.sapphire.logrotate.plist \
  ~/Library/LaunchAgents/com.sapphire.logrotate.plist || \
  diff -u infra/launchagents/com.sapphire.logrotate.plist \
    ~/Library/LaunchAgents/com.sapphire.logrotate.plist
```

If archives were pruned unexpectedly, stop and preserve the remaining `.gz`
files. The script keeps only three archives per log stem, so recovery from an
approved run is usually from backups, not from the working tree.

## Safety Notes

- Do not delete or manually truncate logs during routine inspection.
- Do not unload, bootstrap, kickstart, or retarget the LaunchAgent without an
  explicit ops change.
- Do not replace the repo path in the plist casually; launchd depends on the
  canonical Sapphire checkout path.
- Do not run the script as a "read-only" check.
- Do not paste log contents into issues if they contain tokens, chat IDs, URLs
  with credentials, or sensitive operational context.

## Escalation

Escalate when:

- The installed plist differs from the repo plist.
- stderr shows repeated compression, truncation, or prune failures.
- Logs exceed disk-safe size and the routine is not rotating them.
- Archives are missing after an unexpected manual run.
- Permission fixes would require changing ownership outside the operator home
  directories.

Include launchd state, plist diff if any, last 80 stdout lines, last 40 stderr
lines, `find` size output for the two target directories, and whether the pause
flag exists.
