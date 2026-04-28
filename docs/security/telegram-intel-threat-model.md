# Telegram Intel Reader Threat Model

## Assets

- Telegram channel inventory in local config.
- Local MTProto session at `~/.sapphire/telegram_intel.session`.
- Persisted JSONL corpus under `data/telegram_intel/`.
- Local inference proxy at `127.0.0.1:11435`.

## Trust Boundaries

- Telegram network APIs are outside Sapphire trust.
- The local inference proxy is trusted only for optional classification and must
  time out cleanly.
- The plugin stdin JSON interface is local operator input, not a public API.

## Abuse Paths And Mitigations

- Accidental live collection: daemon and real backend construction require
  `SAPPHIRE_TELEGRAM_INTEL_LIVE=1`, a session file, and enabled config.
- PII persistence: sink stores channel attribution and message ID only; text is
  URL-defanged and common emails, phone numbers, handles, and wallet addresses
  are redacted before provenance stamping.
- Corpus flooding: hard caps enforce 32 enabled channels, 600 messages/hour, and
  200 classifications/hour.
- Prompt leakage to local model: classifier receives sanitized/truncated text,
  uses the local proxy only, and falls back after 5 seconds or invalid JSON.
- Secret exposure: configs do not contain credentials, and the LaunchAgent
  template has no token, password, key, or session value embedded.

## Residual Risk

Channel-level attribution is retained for source quality and provenance. Private
channel names should therefore stay out of committed config and only live in the
local untracked `infra/telegram_channels.yaml`.
