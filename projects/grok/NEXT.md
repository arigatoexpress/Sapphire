# What next (2026-08-06 — post P0-A/B, lunch autonomous)

## DONE (Claude plant)

- free-reign `gate_order` in `executor.py` (`via=free_reign` only) — `43f1cc9`
- genome closes on full lots (`auto_estimate`) — `7a2dea1`
- Bridge green earlier

## NOW

| Priority | Job | Owner |
|---|---|---|
| **1** | Reload `rh-executor` so wired code is live | Claude · [prompt](../../docs/handoffs/CLAUDE-EXECUTOR-RELOAD-PROMPT-2026-08-06.md) |
| **2** | Deploy dashboard SPA fix | Gemini Cloud Shell |
| **3** | Ari: confirm gate scope (free_reign only vs all auto) | Operator |
| **4** | Win P0 | Desk |
| **5** | MOSS grant if wanted | Operator |

## Operator decisions pending

1. **Gate scope:** human Telegram approvals intentionally bypass monorepo policy — OK?
2. **Executor host:** is `rh-executor` Mac, Win, or both?
