# Legacy Telegram Bot Tombstone - 2026-05-11

## Decision

`services/telegram-bot/` was removed from active source.

The active Telegram runtime is now `services/pm_bot/`, backed by the PM bot
webhook on `127.0.0.1:18082` and the local draft queue at
`~/.cache/sapphire/telegram/pm_bot_drafts.jsonl`.

## Why It Was Removed

The legacy service was a second Telegram ingress and egress surface:

- It could call `sendMessage` directly.
- It carried a polling development mode.
- It shelled out to tool/plugin commands as a Telegram UI layer.
- It preserved obsolete Nemotron/Hermes-era assumptions after PM bot became the
  single webhook owner.

Keeping it in `services/` made audits and operator inventories lie about what
owned Telegram.

## Removed Files

- `services/telegram-bot/app.py`
- `services/telegram-bot/Dockerfile`
- `tests/unit/test_telegram_bot_app.py`

Git history is the archive. Do not restore this service unless it is rebuilt as
a PM-bot adapter with no polling path and no direct live-send path.

## Replacement

Use:

- `services/pm_bot/server.py`
- `plugins/claw-sapphire/tools/sapphire_pm_bot.py`
- `lib.telegram.draft_queue`
- `scripts/ops/telegram_sender_audit.py`
