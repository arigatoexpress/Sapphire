# Offline Media Work Orders

Sapphire can turn existing content-engine artifacts into local media work
orders before any image, video, audio, Telegram, or publishing executor runs.

The work-order generator reads `data/content/drafts/*.json`, follows the
ready-platform paths in each draft manifest, and writes:

- `data/media/work_orders/*.json`
- `data/media/manifests/*.json`
- `data/media/runs/<work_order_id>/...` after a dry-run factory run

Both directories are ignored runtime artifacts. The provenance manifest hashes
the source draft, platform renderings, and generated work-order JSON so later
media generation can prove which inputs drove an asset.

## Usage

```bash
python3 -m lib.media work-orders --kind weekly_crypto_brief --kind market_pulse --latest --pretty
```

Use `--latest` for the newest draft per kind. Omit it to generate work orders
for every selected draft, or add `--limit N` while testing.

Validate one or more existing work orders before materializing readiness files:

```bash
python3 -m lib.media validate data/media/work_orders/<work_order_id>.json --pretty
```

Run the dry-run factory for explicit work orders, or omit paths to consume the
JSON files already present in `data/media/work_orders/`:

```bash
python3 -m lib.media run --work-order data/media/work_orders/<work_order_id>.json --pretty
python3 -m lib.media run data/media/work_orders/<work_order_id>.json --pretty
python3 -m lib.media run --limit 1 --pretty
```

Each successful run writes local readiness artifacts under
`data/media/runs/<work_order_id>/`:

- `image/readiness.json` and `image/prompt.md`
- `audio/readiness.json` and `audio/script.txt`
- `video/readiness.json` and `video/storyboard.json`
- `factory_run.json` plus a local provenance manifest

Summarize local runs with:

```bash
python3 -m lib.media status --pretty
python3 -m lib.media status --work-order-id <work_order_id> --pretty
```

## Safety

This command is offline-only:

- no model calls
- no image, video, or speech API calls
- no Telegram sends
- no publish path
- no live market data refresh

The factory rejects work orders unless they keep `dry_run=true`,
`approval_status=pending`, and live/publishing/Telegram flags disabled. The
output remains a dry-run planning artifact; it is readiness for manual review,
not generated media.
