# Sapphire upstream patches

Patches Sapphire maintains against third-party repos it doesn't own.
Applied at install time so they survive reinstalls.

## `hermes-relay-ignore.patch`

**Target:** `NousResearch/hermes-agent` → `gateway/run.py`
**Installed at:** `~/Code/hermes-agent` (or wherever the gateway is checked out)

Adds `TELEGRAM_IGNORED_USER_IDS` env-gated relay-ignore so hermes stops
LLM-replying to bots that exist purely to relay responses back (e.g.
`@rarikimibot` → Kimi Cloud). Without this patch, hermes and the relay bot
form an infinite loop through the Telegram bus.

Also bumps the `agent:start` hook message payload from 500 → 16000 chars so
the kimi-relay-writer hook sees the full user message instead of a truncation.

### Apply

```bash
cd ~/Code/hermes-agent
git apply /path/to/Sapphire/patches/hermes-relay-ignore.patch
```

### Configure

Set the Telegram user IDs to silence in the gateway's env:

```bash
# ~/.hermes/.env
TELEGRAM_IGNORED_USER_IDS=<kimi-relay-bot-user-id>,<other-relay-bot-id>
```

### Upstream status

Not yet proposed upstream. Candidate for a PR to `NousResearch/hermes-agent`.
