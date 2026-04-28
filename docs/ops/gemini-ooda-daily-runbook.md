# Gemini OODA Daily Runbook

The daily Gemini OODA LaunchAgent writes one dry-run OODA packet per day from
the current sovereign-thesis snapshot. It proves the bounded Gemini lane can run
on a production cadence without enabling paid calls or live actions.

## What It Does

`infra/launchagents/com.sapphire.gemini-ooda-daily.plist` runs at 06:30 local
time. It calls `scripts/ops/gemini_ooda_daily.sh`, which changes into the
canonical Sapphire repo, sets `SAPPHIRE_GEMINI_LIVE=0`, and runs
`scripts/ops/gemini_ooda_daily.py`.

The Python wrapper:

- Builds a paste-safe summary from `lib/intel/sovereign_thesis.py`.
- Calls `plugins/claw-sapphire/tools/gemini_ooda.py` with `mode=dry-run`.
- Writes `data/.autonomy/gemini-ooda/<YYYY-MM-DD>.json`.
- Writes a provenance sidecar beside the packet.
- Appends a `priority:p3 type:gemini_ooda_daily` row to
  `data/system_events.jsonl` with only counts and changed keys.

The dashboard endpoint `/api/gemini-ooda?diff=1` exposes the today-versus-
yesterday delta as changed keys and truncated values only. The sovereign-thesis
page renders that delta under the existing Gemini OODA panel.

## How To Enable Or Disable It

Install or refresh the LaunchAgent after merging the repo-side plist:

```bash
cp infra/launchagents/com.sapphire.gemini-ooda-daily.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.gemini-ooda-daily.plist
launchctl kickstart -k gui/$(id -u)/com.sapphire.gemini-ooda-daily
```

Disable it without deleting repo evidence:

```bash
launchctl bootout gui/$(id -u)/com.sapphire.gemini-ooda-daily
rm -f ~/Library/LaunchAgents/com.sapphire.gemini-ooda-daily.plist
```

Check status:

```bash
launchctl print gui/$(id -u)/com.sapphire.gemini-ooda-daily
ls -1 data/.autonomy/gemini-ooda/
tail -20 data/system_events.jsonl
```

## Cost And Safety

Cost is zero by default. The LaunchAgent and wrapper both force
`SAPPHIRE_GEMINI_LIVE=0`, and the underlying OODA tool defaults to a deterministic
mock packet unless `SAPPHIRE_GEMINI_LIVE=1` is explicitly set by a manual
operator session.

This daily path never submits orders, never signs transactions, never sends
Telegram messages, and never writes outside the ignored autonomy and event-log
paths. It is a provenance-stamped production cadence check, not a live Gemini
spend path.

## Verification

Run the focused checks:

```bash
python3 -m pytest tests/unit/test_gemini_ooda_daily.py tests/unit/test_launchagent_plists.py -q
python3 -m pytest tests/integration/test_dashboard_endpoints.py -q
plutil -lint infra/launchagents/com.sapphire.gemini-ooda-daily.plist
```

Manual dry-run:

```bash
scripts/ops/gemini_ooda_daily.sh --pretty
python3 scripts/ops/provenance_verify.py --pretty
```
