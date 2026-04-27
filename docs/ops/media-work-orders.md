# Offline Media Work Orders

Sapphire can turn existing content-engine artifacts into local media work
orders before any image, video, audio, Telegram, or publishing executor runs.

The work-order generator reads `data/content/drafts/*.json`, follows the
ready-platform paths in each draft manifest, and writes:

- `data/media/work_orders/*.json`
- `data/media/manifests/*.json`

Both directories are ignored runtime artifacts. The provenance manifest hashes
the source draft, platform renderings, and generated work-order JSON so later
media generation can prove which inputs drove an asset.

## Usage

```bash
python3 -m lib.media work-orders --kind weekly_crypto_brief --kind market_pulse --latest --pretty
```

Use `--latest` for the newest draft per kind. Omit it to generate work orders
for every selected draft, or add `--limit N` while testing.

## Safety

This command is offline-only:

- no model calls
- no image, video, or speech API calls
- no Telegram sends
- no publish path
- no live market data refresh

The output is a dry-run planning artifact with `approval_status=pending`.
