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
- Offline history import: `import-history` reads local Telegram Desktop JSON
  exports without live Telegram API access and writes sanitized history/context
  artifacts under `data/telegram_history_intel/`.
- Caps: 32 enabled channels, 600 messages/hour, 200 local-model
  classifications/hour, 8000 characters per stored message.
- Channel schema: `id`, `category`, `weight`, `backend`, `enabled`, and `notes`;
  `source`, `botapi`, `pull_limit_per_channel`, and `min_quality` remain
  backward-compatible aliases.
- Optional classifier: local inference proxy at `127.0.0.1:11435`, model alias
  `balanced`, 5 second timeout, heuristic fallback.
- Dashboard summary: `/api/telegram-history-intel` exposes aggregate offline
  history counts, artifact sidecar posture, sanitized signal previews, and a
  no-send/no-live-API safety envelope behind dashboard auth.

## Non-Goals

- No real Telegram sends.
- No automatic access to the operator's Telegram account or chat history.
- No committed real Telegram exports or imported history artifacts.
- No trading critical path integration.
- No committed private channel inventory.
- No persistence of Telegram sender IDs, sender handles, phone numbers, email
  addresses, wallet addresses, or raw clickable URLs.

## Offline History Context

`services.telegram_intel.history_export` turns operator-provided Telegram Desktop
JSON into two local artifacts:

- `messages.jsonl`: provenance-stamped rows with hashed chat/participant IDs,
  sanitized text, media kind, reply linkage, link domains, tags, and
  open-loop/commitment/decision signals.
- `conversation_context.json`: deterministic aggregate context for chats,
  participants, tags, open loops, commitments, and decisions.

This is the first read-only bridge from personal Telegram history into the
Sapphire intel pipeline. It is designed for local recall, audit, and future
dashboarding, not for unreviewed sharing.
