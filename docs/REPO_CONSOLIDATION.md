# Repo Consolidation Map

Sapphire is the canonical trading runtime and control plane for this org.
The repos listed below were consolidated into Sapphire (or retired) to reduce duplication and keep agentic navigation simple.

## Superseded / Archived Trading Repos

| Repo | Status | Replacement / Notes |
|------|--------|---------------------|
| `arigatoexpress/quant-ai-trader` | Archived | Superseded by `arigatoexpress/Sapphire`. Retained for historical reference. |
| `arigatoexpress/binance-trade-bot` | Archived (fork) | Superseded by `arigatoexpress/Sapphire`. Fork retained for reference only. |
| `arigatoexpress/freqtrade` | Archived (fork) | Superseded by `arigatoexpress/Sapphire`. Fork retained for reference only. |
| `arigatoexpress/freqtrade-strategies` | Archived (fork) | Superseded by `arigatoexpress/Sapphire`. Fork retained for reference only. |
| `arigatoexpress/tensortrade` | Archived (fork) | Superseded by `arigatoexpress/Sapphire`. Fork retained for reference only. |
| `arigatoexpress/FreedomBot` | Archived | Source preserved at `archive/external/freedombot/`. |
| `arigatoexpress/fullsail_scanner` | Archived | Source preserved at `tools/sui_event_scanner/`. |

## Why This Exists

Goals:
- Keep one canonical repo for trading execution + ops.
- Keep historical prototypes available without keeping them “active”.
- Reduce duplicated CI/deploy/docs surface area across repos.
