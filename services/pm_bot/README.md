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
  2. `TELEGRAM_BOT_TOKEN=...` — share the existing Sapphire bot that `notify` / `watchdog` / etc. already use (recommended — one less token to rotate)
  3. `~/.config/sapphire-secrets/telegram_bot_token` — file fallback (same location used by `plugins/claw-sapphire/tools/notify.py`)
  4. `~/.config/sapphire/telegram_bot_token` — legacy file location
- `SAPPHIRE_PM_BOT_ALLOWED_USER_IDS=12345,67890`

Optional:

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
- `SAPPHIRE_PM_BOT_HOST=127.0.0.1`
- `SAPPHIRE_PM_BOT_PORT=18082`
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
MODE=polling python3 server.py
```

`MODE=polling` is intended for local development. Telegram must not still have a webhook registered for the same bot token when polling is active; the service attempts `deleteWebhook` on startup in polling mode.

## Register The Webhook

The webhook URL must be publicly reachable. In practice that means a tunnel such as Tailscale Funnel or another HTTPS endpoint that forwards to `http://127.0.0.1:18082/telegram/webhook`.

Set the webhook:

```bash
curl -s "https://api.telegram.org/bot${SAPPHIRE_PM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://YOUR-PUBLIC-URL/telegram/webhook\",\"allowed_updates\":[\"message\"],\"secret_token\":\"${SAPPHIRE_PM_BOT_WEBHOOK_SECRET}\"}"
```

Clear the webhook for polling:

```bash
curl -s "https://api.telegram.org/bot${SAPPHIRE_PM_BOT_TOKEN}/deleteWebhook" \
  -H "Content-Type: application/json" \
  -d '{"drop_pending_updates":false}'
```

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
