# Claude — reload rh-executor so gate is live (short)

```text
Mac plant. P0-A/B source already wired in ~/ops-state/telegram-bot/executor.py
(commits 43f1cc9 + 7a2dea1). Live rh-executor schtask/process may still run OLD code.

MISSION:
1. Confirm which process/schtask runs executor.py (Mac and/or Win).
2. Gracefully restart ONLY that executor process so it reloads the wired file.
3. Do NOT ARM L2. Do NOT place live orders. Do NOT kill sapphire_os / plant deck.
4. Verify: free-reign dry proposal that would hit DENS_BLOCK logs gate-denied (or unit path).
5. Export: data/grok-web-exports/YYYY-MM-DD_local-export_executor-reloaded.md
6. Commit local-export: rh-executor reloaded with gate_order [date]

If Win hosts rh-executor and Win is down: document BS-EXECUTOR-DEPLOY blocked on Win P0; stop.
```
