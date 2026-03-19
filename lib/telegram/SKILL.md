---
name: sapphire-telegram
description: Telegram bot framework — handlers, commands, notification routing, agent dispatch
type: library
runtime: python
deploy_target: rari1
dependencies: [sapphire-core]
entry_point: src/sapphire_telegram/bot.py
test_command: pytest tests/
---

# sapphire.telegram

Shared Telegram bot framework used by control-plane and lighter services. Handles bot lifecycle, command routing, and outbound notifications.

## Key Modules

- `bot.py` — Bot init, webhook/polling mode switch, startup validator
- `handlers.py` — Command handlers: /status, /pnl, /deploy, /task, /alert

## Usage

```python
from sapphire_telegram.bot import SapphireBot

bot = SapphireBot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
bot.run_polling()
```

## Notification Routing

Outbound notifications are tagged before send:
- `priority:p0` → immediate push, bypass quiet hours
- `type:trading` → trading channel
- `agent:kimi` → Kimi status channel

## Deploy Notes

- Runs on rari1 as part of control-plane service
- Bot token in Secret Manager: `sapphire-telegram-bot-token`
- Webhook URL (Cloud Run): `https://pm.sapphirealpha.xyz/telegram/webhook`
