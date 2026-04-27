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
```

The commands above are previews. They do not write files unless `--write` is
passed explicitly.

## Files

When explicitly enabled, records are appended under the ignored directory:

```text
data/.autonomy/continuous_intelligence/task_snapshots.jsonl
data/.autonomy/continuous_intelligence/task_leases.jsonl
data/.autonomy/continuous_intelligence/task_results.jsonl
```

These paths are intentionally ignored by git. They are runtime evidence, not
source.

## Dashboard

Read-only endpoints:

```text
GET /api/autonomy/continuous-intelligence/artifacts
GET /api/autonomy/continuous-intelligence/lease-preview
```

Both endpoints keep `write_enabled=false`, `execution_enabled=false`,
`live_trading_enabled=false`, and `telegram_sends_enabled=false`.

## Safety

- Writes are opt-in at the module/CLI layer.
- Dashboard endpoints are status/preview only.
- Leases are dry-run records, not execution grants.
- Result records reject obvious secret-bearing keys before optional writes.
- Live trading, payment, Telegram, broker, and wallet-signing paths remain off.

## Next

After this lands, the next reversible step is a tiny local LaunchAgent or
scheduled command that runs `snapshot --write` and `lease --write` against
approved dry-run worker IDs. Worker execution should still wait until task
results have schema validation and dashboard review.
