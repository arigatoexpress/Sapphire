# Telegram Intel Reader Threat Model

## Assets

- Telegram channel inventory in local config at
  `~/.sapphire/telegram_channels.yaml`.
- Local MTProto session at `~/.sapphire/telegram_intel.session`.
- Persisted JSONL corpus under `data/telegram_intel/`.
- Offline Telegram Desktop history exports selected by the operator.
- Sanitized offline history corpus under `data/telegram_history_intel/`.
- Local inference proxy at `127.0.0.1:11435`.

## Trust Boundaries

- Telegram network APIs are outside Sapphire trust.
- Telegram Desktop exports are untrusted local inputs and may contain private
  conversations, sender names, handles, phones, emails, links, and media
  metadata.
- The local inference proxy is trusted only for optional classification and must
  time out cleanly.
- The plugin stdin JSON interface is local operator input, not a public API.

## Abuse Paths And Mitigations

- Accidental live collection: daemon and real backend construction require
  `SAPPHIRE_TELEGRAM_INTEL_LIVE=1`, a session file, and enabled config.
- PII persistence: sink stores channel attribution and message ID only; text is
  URL-defanged and common emails, phone numbers, handles, and wallet addresses
  are redacted before provenance stamping.
- Offline history import is API-free and stores hashed chat/participant IDs by
  default. It does not persist raw chat names, sender names, forwarded handles,
  export file names, sender IDs, clickable URLs, emails, phones, or wallet
  addresses.
- Export leakage: real Telegram exports and `data/telegram_history_intel/` are
  local-only artifacts and ignored by git. Use synthetic fixtures only in tests.
- Context overexposure: `conversation_context.json` stores deterministic counts,
  tags, and short sanitized snippets for open loops, commitments, and decisions;
  it is not a raw conversation archive.
- Corpus flooding: hard caps enforce 32 enabled channels, 600 messages/hour, and
  200 classifications/hour.
- Source weighting abuse: channel `weight` is clamped and applied
  deterministically to the local quality score only, never as a live execution
  permission.
- Prompt leakage to local model: classifier receives sanitized/truncated text,
  uses the local proxy only, and falls back after 5 seconds or invalid JSON.
- Secret exposure: configs do not contain credentials, and the LaunchAgent
  template has no token, password, key, or session value embedded.

## Residual Risk

Channel-level attribution is retained for source quality and provenance. Private
channel names should therefore stay out of committed config and only live in the
local untracked `~/.sapphire/telegram_channels.yaml`.

Offline history imports can still contain sensitive business context after
redaction. Treat `data/telegram_history_intel/` as local operator evidence, not
as a buyer-shareable artifact, unless it has been reviewed separately.
