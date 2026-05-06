# Continuous Intelligence Artifacts

Date: 2026-04-27

## Decision

Continuous intelligence needs a local artifact contract before any scheduler or
worker starts doing real work. This PR adds an opt-in JSONL sink for task
snapshots, dry-run leases, and reviewed task results:

```bash
python3 -m lib.autonomy.continuous_intelligence_artifacts status --pretty
python3 -m lib.autonomy.continuous_intelligence_artifacts snapshot --pretty
python3 -m lib.autonomy.continuous_intelligence_artifacts lease \
  --agent-id windows-gpu --target-runtime windows-gpu --limit 2 --pretty
python3 -m lib.autonomy.continuous_intelligence_artifacts daily-packet --pretty
```

The commands above are previews. They do not write files unless `--write` is
passed explicitly.

## Files

When explicitly enabled, records are appended under the ignored directory:

```text
data/.autonomy/continuous_intelligence/task_snapshots.jsonl
data/.autonomy/continuous_intelligence/task_leases.jsonl
data/.autonomy/continuous_intelligence/task_results.jsonl
data/.autonomy/continuous_intelligence/daily_autonomy_packets.jsonl
data/.autonomy/continuous_intelligence/daily_autonomy_packet_latest.json
```

These paths are intentionally ignored by git. They are runtime evidence, not
source.

## Daily Packet

The scheduled packet is artifact-only:

```bash
python3 -m lib.autonomy.continuous_intelligence_artifacts daily-packet \
  --write --pretty
```

It appends a task snapshot, appends dry-run leases for `mac-local` and
`windows-gpu`, appends a daily packet row, and refreshes a latest JSON pointer.
It does not dispatch workers, call Telegram, change trading state, or promote
tasks without review.

## Dashboard

Read-only endpoints:

```text
GET /api/autonomy/continuous-intelligence/artifacts
GET /api/autonomy/continuous-intelligence/lease-preview
```

Both endpoints keep `write_enabled=false`, `execution_enabled=false`,
`live_trading_enabled=false`, and `telegram_sends_enabled=false`.

The `/sovereign-thesis` page renders these same surfaces as a read-only control
panel: next dispatch tasks, local artifact status, and Windows GPU lease
previews.

## Safety

- Writes are opt-in at the module/CLI layer.
- Dashboard endpoints are status/preview only.
- Leases are dry-run records, not execution grants.
- Result records reject obvious secret-bearing keys before optional writes.
- Live trading, payment, Telegram, broker, and wallet-signing paths remain off.

## Next

The local LaunchAgent
`infra/launchagents/com.sapphire.continuous-intelligence-daily.plist` runs the
daily packet at 06:45 local time. Worker execution should still wait until task
results have schema validation and dashboard review.
