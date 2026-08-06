# Claude plant — refresh desk trading intelligence on public wire

**When:** after usage limit + after/with executor reload  
**Why:** Public MC looks empty because `desk` in `/api/v1/live` is stale/null while machine room is fine.

```text
MISSION: Make desk + markets decision fields truthful on the signed telemetry
publisher — not fake, not wallet leaks.

1. Find alpha-telemetry-publisher / merged_collector (dashboard repo telemetry/
   + infra/com.sapphire.alpha-telemetry-publisher.plist on Mac).
2. Ensure each publish cycle fills desk:
   - posture, execution, safety_floor, epistemics.regime when known
   - updated_at = now (ISO UTC)
   - if unknown, omit or set explicit unknown + do not reuse 11h-old blob
3. markets.decision_gate / execution from real free-reign/pause if available
4. paper_strategies from paper lab only if real
5. Optional: research public clip via admitted path only
6. Never put wallets, balances, positions, order ids in telemetry
7. Verify: curl https://sapphirealpha.xyz/api/v1/live desk.updated_at is fresh
8. Export local-export: telemetry desk refresh [date]

Also complete executor reload if not done:
docs/handoffs/CLAUDE-RESUME-EXECUTOR-RELOAD-2026-08-06.md

NO L2 ARM. NO live orders for testing.
```
