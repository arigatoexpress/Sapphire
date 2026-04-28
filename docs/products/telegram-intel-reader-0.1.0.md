# Telegram Intel Reader 0.1.0

The Telegram Intel Reader collects enabled channel posts into a local Sapphire
JSONL corpus for later search, dashboarding, and operator review. Version 0.1.0
is intentionally conservative: it reads only when live gates pass, stores no
sender identity, defangs URLs, redacts common PII patterns, and stamps every
persisted record with `lib/core/provenance.py`.

## Capabilities

- Runtime config: operator copies `infra/telegram_channels.example.yaml` to
  `~/.sapphire/telegram_channels.yaml`; no real channel list is committed.
- Backends: `mtproto` through Telethon and `bot` through Telegram Bot API
  channel posts visible to the bot.
- Sink: `data/telegram_intel/YYYY-MM-DD/messages.jsonl`.
- Plugin actions: `status`, `pull-once`, `recent`, `quality-test`, `models`.
- Caps: 32 enabled channels, 600 messages/hour, 200 local-model
  classifications/hour, 8000 characters per stored message.
- Channel schema: `id`, `category`, `weight`, `backend`, `enabled`, and `notes`;
  `source`, `botapi`, `pull_limit_per_channel`, and `min_quality` remain
  backward-compatible aliases.
- Optional classifier: local inference proxy at `127.0.0.1:11435`, model alias
  `balanced`, 5 second timeout, heuristic fallback.

## Non-Goals

- No real Telegram sends.
- No trading critical path integration.
- No committed private channel inventory.
- No persistence of Telegram sender IDs, sender handles, phone numbers, email
  addresses, wallet addresses, or raw clickable URLs.
