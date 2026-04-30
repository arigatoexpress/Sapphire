# Telegram Intel Reader Runbook

## Configure

1. Copy `infra/telegram_channels.example.yaml` to
   `~/.sapphire/telegram_channels.yaml`.
2. Set enabled channels to `true` only after verifying the source is intended
   for Sapphire ingestion.
3. Create the MTProto session outside the repo at
   `~/.sapphire/telegram_intel.session`.
4. Keep credentials in the process environment or local secret files, never in
   the YAML config.

Channel entries use this runtime schema:

```yaml
defaults:
  backend: mtproto
  poll_interval_seconds: 300
  max_messages_per_poll: 25
  min_quality_score: 0.45
  min_message_length: 32

channels:
  - id: "@public_handle_or_numeric_channel_id"
    category: security
    weight: 1.0
    backend: mtproto
    enabled: true
    notes: Operator-only context kept outside git.
```

Valid categories are `crypto`, `macro`, `ai`, `security`, `trading`, and
`governance`. Backward-compatible aliases still parse: `source`,
`pull_limit_per_channel`, `min_quality`, and `backend: botapi`.

## Run Safely

Status is always safe and does not contact Telegram:

```bash
/usr/local/bin/python3 services/telegram_intel/run.py status
```

One live pull requires all live gates:

```bash
SAPPHIRE_TELEGRAM_INTEL_LIVE=1 \
  /usr/local/bin/python3 services/telegram_intel/run.py pull-once \
  --config ~/.sapphire/telegram_channels.yaml
```

The LaunchAgent plist under `services/telegram_intel/launchagent/` is a template
only. It ships with `SAPPHIRE_TELEGRAM_INTEL_LIVE=0` and `RunAtLoad=false`.
Do not load it until the config, session, and logs directory have been checked.

## Import Offline History

Telegram Desktop JSON exports can be imported without contacting Telegram,
loading an MTProto session, or enabling the live reader. Export from Telegram
Desktop with JSON format, then point Sapphire at the local export file or
directory:

```bash
/usr/local/bin/python3 services/telegram_intel/run.py import-history \
  --export-path ~/Downloads/Telegram\ Desktop/DataExport_*/result.json \
  --data-dir data/telegram_history_intel
```

The importer writes two local-only artifacts:

- `data/telegram_history_intel/messages.jsonl` — sanitized, provenance-stamped
  message rows with hashed chat and participant identifiers.
- `data/telegram_history_intel/conversation_context.json` — deterministic
  summaries for chat counts, top tags, open loops, commitments, and decisions.

Both artifacts get `.envelope.json` sidecars. The default output directory is
ignored by git. Do not commit real Telegram exports or imported history.

By default, chat names, sender names, export file names, sender IDs, forwarded
handles, emails, phone numbers, wallet addresses, and clickable URLs are not
persisted. `--include-title-hints` exists for local operator triage only and
stores sanitized/truncated chat title hints; leave it off for shareable
artifacts.

Plugin stdin action:

```json
{
  "action": "import-history",
  "export_path": "/absolute/path/to/result.json",
  "data_dir": "data/telegram_history_intel"
}
```

Dashboard summary is available after import at `/api/telegram-history-intel`
behind normal dashboard auth. `/api/intel` also includes a source row with
Telegram history availability, message count, freshness, artifact sidecar
presence, and the read-only/no-send safety envelope.

## Validate

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_dashboard_telegram_history_intel.py \
  tests/unit/test_telegram_intel_reader.py \
  tests/unit/test_telegram_history_export.py \
  tests/unit/test_telegram_intel_quality.py \
  tests/unit/test_telegram_intel_sink.py \
  plugins/claw-sapphire/tests/test_telegram_intel.py -q

/usr/local/bin/python3 scripts/validate_tool_registry.py
```

## Rollback

Stop the LaunchAgent if it was loaded, set `SAPPHIRE_TELEGRAM_INTEL_LIVE=0`,
and revert the feature PR. The local JSONL corpus is append-only and can be
archived by moving `data/telegram_intel/` out of the repo.
