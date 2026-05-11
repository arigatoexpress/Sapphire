# Sapphire PM Bot

Minimal Telegram-first PM surface for Sapphire phase 1. The service receives Telegram webhook or polling updates, hands them to [`sapphire_pm_bot`](../../plugins/claw-sapphire/tools/sapphire_pm_bot.py), and sends the formatted response back through the Telegram Bot API.

## Prerequisites

- Python 3.11+
- Application Default Credentials already configured on the Mac:
  - `gcloud auth application-default login`
- Service deps installed:
  - `pip install -r /Users/aribs/Code/Sapphire/services/pm_bot/requirements.txt`

## Environment Variables

Required:

- Telegram bot token — resolved in this priority order:
  1. `SAPPHIRE_PM_BOT_TOKEN=123456:abc` — explicit override for a dedicated PM bot
  2. `TELEGRAM_BOT_TOKEN=...` — shared Sapphire bot used by `notify` / `watchdog` / Hermes
  3. `~/.config/sapphire-secrets/telegram_bot_token` — file fallback (same location used by `plugins/claw-sapphire/tools/notify.py`)
  4. `~/.config/sapphire/telegram_bot_token` — legacy file location
- `SAPPHIRE_PM_BOT_ALLOWED_USER_IDS=12345,67890`
- `SAPPHIRE_PM_BOT_ALLOWED_USER_IDS_FILE=~/.config/sapphire-secrets/sapphire_pm_bot_allowed_user_ids`
  - File-backed allowlist for LaunchAgent deployments. Contents should be a
    comma-separated list of numeric Telegram user IDs. If both the env var and
    file path are set, the env var wins.

Optional:

- `SAPPHIRE_PM_BOT_BOT_USERNAME=SapphirePMBot`
  - Enables guest-style mention parsing such as `@SapphirePMBot status` and
    reply-followup shorthand like replying `status` to the bot in group chats.
    The service can also fall back to Telegram `getMe` during health probing if
    this env var is missing or stale.
- `SAPPHIRE_PM_BOT_WEBHOOK_SECRET=...`
  - Recommended for webhook mode. The service compares this against
    Telegram's `X-Telegram-Bot-Api-Secret-Token` header and rejects bad
    requests with `403` before parsing JSON.
- `TELEGRAM_WEBHOOK_SECRET=...`
  - Shared fallback if `SAPPHIRE_PM_BOT_WEBHOOK_SECRET` is not set.
- `~/.config/sapphire-secrets/sapphire_pm_bot_webhook_secret`
  - File fallback for LaunchAgent deployments; avoids embedding secret values in plists.
- `~/.config/sapphire-secrets/telegram_webhook_secret`
  - Shared file fallback for the same webhook secret.
- `THO_API_KEY_FILE=~/.config/sapphire-secrets/tho_api_key`
  - Required for `/rag`; prefer the file path over putting `THO_API_KEY` directly in the LaunchAgent environment
- `THO_API_KEY=...`
  - Supported for local development only
- `MODE=webhook`
  - Set `MODE=polling` for local long-poll development
- `SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING=1`
  - Break-glass only. Polling mode normally refuses to start with the shared
    Sapphire Telegram token because it competes with Hermes or webhook consumers.
- `SAPPHIRE_PM_BOT_HOST=127.0.0.1`
- `SAPPHIRE_PM_BOT_PORT=18082`
- `SAPPHIRE_PM_BOT_PROBE_TIMEOUT_SECONDS=2`
  - Dedicated timeout for read-only `getMe` / `getWebhookInfo` health probes.
    Keep this short so local `/health` remains responsive when Telegram is slow.
- `THO_API_BASE_URL=https://project-go-forward-trgi34bxuq-uc.a.run.app`
- `THO_FIRESTORE_PROJECT=tho-ai-agent`
- `SAPPHIRE_PM_BOT_DEFAULT_PROJECT_ID=<firestore-project-id>`
  - Optional override for `/pm new` if project auto-detection is not enough

## Run Locally

Webhook mode:

```bash
cd /Users/aribs/Code/Sapphire/services/pm_bot
MODE=webhook python3 -m uvicorn server:app --host 127.0.0.1 --port 18082
```

Polling mode:

```bash
cd /Users/aribs/Code/Sapphire/services/pm_bot
SAPPHIRE_PM_BOT_TOKEN=123456:dedicated-pm-token MODE=polling python3 server.py
```

`MODE=polling` is intended for local development with a dedicated PM bot token. The service refuses to poll with `TELEGRAM_BOT_TOKEN` or the shared token files unless `SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING=1` is set for a deliberate break-glass run. Telegram must not still have a webhook registered for the same bot token when polling is active; the service attempts `deleteWebhook` on startup in polling mode. If you are testing against the shared Sapphire bot token, verify no other Telegram consumer is actively polling it first.

## Register The Webhook

The webhook URL must be publicly reachable. In practice that means a tunnel such as Tailscale Funnel or another HTTPS endpoint that forwards to `http://127.0.0.1:18082/telegram/webhook`.

Plan the webhook registration first. This does not call Telegram or mutate the
bot:

```bash
python3 scripts/ops/pm_bot_webhook_readiness.py \
  --url "https://YOUR-PUBLIC-URL/telegram/webhook" \
  --json
```

Apply is deliberately double-gated because it mutates Telegram delivery state:

```bash
SAPPHIRE_PM_BOT_REGISTER_WEBHOOK_APPLY=1 \
python3 scripts/ops/pm_bot_webhook_readiness.py \
  --url "https://YOUR-PUBLIC-URL/telegram/webhook" \
  --apply \
  --json
```

The equivalent raw Bot API call is:

```bash
curl -s "https://api.telegram.org/bot${SAPPHIRE_PM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://YOUR-PUBLIC-URL/telegram/webhook\",\"allowed_updates\":[\"message\",\"edited_message\",\"channel_post\",\"edited_channel_post\",\"business_connection\",\"business_message\",\"edited_business_message\",\"deleted_business_messages\",\"guest_message\",\"callback_query\",\"message_reaction\",\"message_reaction_count\",\"inline_query\",\"chosen_inline_result\",\"shipping_query\",\"pre_checkout_query\",\"purchased_paid_media\",\"poll\",\"poll_answer\",\"my_chat_member\",\"chat_member\",\"chat_join_request\",\"chat_boost\",\"removed_chat_boost\",\"managed_bot\"],\"secret_token\":\"${SAPPHIRE_PM_BOT_WEBHOOK_SECRET}\"}"
```

The service routes this full Bot API update surface through
`lib.telegram.agent_router`. Only `command` routes can call `sendMessage`; all
other routes are accepted as no-send router decisions and queued as local
dry-run draft/event records when `SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED` is true.

Set `SAPPHIRE_PM_BOT_WEBHOOK_URL` on the runtime once a public URL is chosen.
Health then treats a different registered webhook as `webhook_url_mismatch`
instead of a false green.

Clear the webhook for polling:

```bash
curl -s "https://api.telegram.org/bot${SAPPHIRE_PM_BOT_TOKEN}/deleteWebhook" \
  -H "Content-Type: application/json" \
  -d '{"drop_pending_updates":false}'
```

## Health Endpoint

`GET /health` now reports not just local process state, but Telegram delivery
readiness as seen from the Bot API. In webhook mode this makes it obvious when
the service is healthy locally but Telegram still has no webhook registered.
The read-only Bot API probe is cached for 60 seconds and uses
`SAPPHIRE_PM_BOT_PROBE_TIMEOUT_SECONDS` so local liveness does not block on the
longer operational Telegram timeout.

Key fields:

- `bot_username`
  - Prefers the configured env var, but falls back to a read-only `getMe`
    probe so stale LaunchAgent environment does not hide the real bot username.
- `supported_update_types`
  - The update types this service is prepared to parse.
- `telegram_delivery_ready`
  - `true` only when the configured delivery mode is actually ready:
    registered webhook in `MODE=webhook`, or live polling thread in
    `MODE=polling`.
- `telegram_delivery_reason`
  - One of `webhook_registered`, `webhook_missing`, `webhook_url_mismatch`,
    `polling_active`, `polling_inactive`, or `probe_failed`.
- `telegram_probe_ok`
  - Whether the read-only Telegram readiness probe succeeded.
- `telegram_webhook_registered`
  - Whether Telegram currently has a webhook URL for this bot token.
- `telegram_webhook_url_configured`
  - Whether `SAPPHIRE_PM_BOT_WEBHOOK_URL` is configured.
- `telegram_webhook_url_matches_expected`
  - `true` only when Telegram's registered webhook matches
    `SAPPHIRE_PM_BOT_WEBHOOK_URL`; `null` when no expected URL is configured.
- `telegram_pending_update_count`
  - Bot API pending update count when available.
- `telegram_allowed_updates`
  - Bot API allowed update list when available.

`GET /telegram/ownership` is the shorter operator gate for the future private
agent group. It reports the single-ingress owner, whether the group is ready,
the current blockers, and the no-send router guard. Use it before inviting Kimi
or Nemotron into a shared group.

## LaunchAgent

The LaunchAgent plist ships here:

- [`services/pm_bot/launchagent/com.sapphire.pm-bot.plist`](/Users/aribs/Code/Sapphire/services/pm_bot/launchagent/com.sapphire.pm-bot.plist)

Install manually when ready:

```bash
cp /Users/aribs/Code/Sapphire/services/pm_bot/launchagent/com.sapphire.pm-bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sapphire.pm-bot.plist
```

Logs go to:

- `~/Library/Logs/sapphire-pm-bot.log`

## Test Recipe

Tool tests:

```bash
cd /Users/aribs/Code/Sapphire
pytest plugins/claw-sapphire/tests/test_sapphire_pm_bot.py -q
```

Full plugin suite:

```bash
cd /Users/aribs/Code/Sapphire
pytest plugins/claw-sapphire/tests/ -q
```

Quick manual smoke test with the service running:

- DM the bot `/help`
- DM the bot `/status`
- DM the bot `/pm list`
- DM the bot `/rag what forms are needed for a sale in Harris County`
- In a group, tag the bot with `@SapphirePMBot status` if `SAPPHIRE_PM_BOT_BOT_USERNAME` is set
- Reply to one of the bot's messages with `status` to exercise reply-followup normalization

For LaunchAgent deployments, keep the shared Sapphire Telegram token owned by
Hermes polling. The PM bot should stay local/webhook-only unless it has a
dedicated `SAPPHIRE_PM_BOT_TOKEN`.

Safe live-test setup:

1. put your numeric Telegram user ID in `~/.config/sapphire-secrets/sapphire_pm_bot_allowed_user_ids`
2. keep the plist in `MODE=webhook`
3. register a PM-bot webhook for the shared token, or use a dedicated `SAPPHIRE_PM_BOT_TOKEN` before switching to `MODE=polling`
4. reload the LaunchAgent and confirm `/health` reports `local_process_ready=true`; `telegram_delivery_ready=false` with `telegram_delivery_reason=webhook_missing` means the local service is up but Telegram is still owned elsewhere or the webhook has not been registered
