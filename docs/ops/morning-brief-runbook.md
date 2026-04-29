# Morning Brief Runbook

Last reviewed: 2026-04-29

This runbook covers `com.sapphire.morning-brief`, the local LaunchAgent that
builds the canonical daily intelligence brief and sends it through the shared
Telegram notification path. This is an operator-information surface only; it
does not approve trades.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.morning-brief.plist` |
| Script | `services/intelligence/daily_brief.py` |
| Working directory | `/Users/aribs/Code/Sapphire` |
| Output artifact | `data/intelligence/YYYY-MM-DD/daily_brief.md` |
| Stdout log | `data/logs/morning-brief.log` |
| Stderr log | `data/logs/morning-brief-err.log` |
| Pause flag | `/Users/aribs/.sapphire/routine_pause/morning-brief` |
| Telegram helper | `notify.send_telegram_message(..., priority="p1")` |

## Schedule

The plist runs daily at 06:00 local:

```bash
/usr/local/bin/python3 /Users/aribs/Code/Sapphire/services/intelligence/daily_brief.py
```

It sets `HOME`, `PYTHONPATH=/Users/aribs/Code/Sapphire`, and
`SAPPHIRE_SECRETS_DIR=/Users/aribs/.config/sapphire-secrets`.

## Data Flow

```text
launchd daily 06:00 local
  -> services/intelligence/daily_brief.py
  -> abort_if_paused("morning-brief")
  -> read market intel, predictions, threats, risk, and health context
  -> write data/intelligence/YYYY-MM-DD/daily_brief.md
  -> send Telegram p1 digest through notify.py
```

The script degrades missing sections into "missing", "unavailable", or "error"
text. Missing source artifacts are a quality issue, not necessarily a daemon
crash.

## Normal Operation

Validate plist syntax and state:

```bash
plutil -lint infra/launchagents/com.sapphire.morning-brief.plist
launchctl print gui/$(id -u)/com.sapphire.morning-brief
```

Inspect logs:

```bash
tail -n 100 data/logs/morning-brief.log
tail -n 100 data/logs/morning-brief-err.log
```

Inspect recent artifacts:

```bash
find data/intelligence -maxdepth 2 -name daily_brief.md -print | sort | tail -7
```

Generate without Telegram when writing a local artifact is acceptable:

```bash
/usr/local/bin/python3 services/intelligence/daily_brief.py --dry-run
```

Important: `--dry-run` avoids Telegram, but it still writes
`data/intelligence/YYYY-MM-DD/daily_brief.md`. It is not strict read-only.

## Strict Read-Only Inspection

Use only file and log inspection:

```bash
tail -n 80 data/logs/morning-brief.log
tail -n 80 data/logs/morning-brief-err.log
find data/intelligence -maxdepth 2 -name daily_brief.md -print | sort | tail
test -f data/intelligence/latest/market_intel.json && \
  jq '{timestamp, errors}' data/intelligence/latest/market_intel.json
```

Do not run the script for strict read-only work.

## Common Failures

### Telegram Send Failed

`notify.py` returns explicit errors when token or chat ID resolution fails. Do
not print token files or `.env` contents into tickets. Check only whether the
expected secret files exist.

### Dry Run Wrote A File

That is expected. The dry-run flag suppresses Telegram, not persistence. Preserve
the generated file if investigating a formatting regression.

### Missing Source Sections

Kronos predictions, market intel, threats, liquidation/cascade, and health
sections can degrade independently. Fix the producer that owns the missing
artifact instead of patching the brief text to hide the gap.

### Routine Pause

`abort_if_paused("morning-brief")` exits before building the brief. A clean exit
can therefore mean skipped.

### Artifact Path Drift

The script writes dated artifacts under `data/intelligence/YYYY-MM-DD/`. Some
routine-health docs historically referenced `data/intelligence/latest/daily_brief.md`.
Treat `latest` as a follow-up integration gap unless a sync process is verified.

## Recovery

Use this order:

1. Confirm the plist is loaded and last exit status.
2. Check pause flags and logs.
3. Inspect the latest dated `daily_brief.md`.
4. If no Telegram landed, inspect notify error text without exposing secrets.
5. Re-run `--dry-run` only when writing a new dated artifact is acceptable.

Focused tests:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_daily_brief_helpers.py \
  tests/unit/test_launchagent_plists.py \
  tests/unit/test_routine_pause.py -q
```

## Safety Notes

- Do not send real Telegram test messages while writing or auditing docs.
- Do not run the non-dry-run script unless a real p1 digest is desired.
- Do not expose token, chat ID, or `.env` contents.
- Do not treat brief recommendations as trade authorization.
- Do not bootstrap, unload, kickstart, or retarget the LaunchAgent during a
  read-only inspection.

## Escalation

Escalate when:

- The brief did not run on schedule and no pause flag explains it.
- Telegram send fails repeatedly with valid secret presence.
- The generated brief contains malformed Markdown or materially wrong market
  context.
- Source artifacts are stale enough to make the brief misleading.
- The installed plist differs from the repo plist.

Include launchd state, last 100 log lines, latest dated artifact path, notify
error text with secrets redacted, source freshness notes, and whether a dry-run
was executed.
