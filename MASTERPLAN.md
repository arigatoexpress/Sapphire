# MASTERPLAN

## Goal
Operate Sapphire as a profitable, 24/7 autonomous trading organization with strict downside protection and owner override through Telegram.

## Scope Lock
- Active repository: `arigatoexpress/Sapphire` only.
- OpenClaw agents and skills are restricted to Sapphire scope until explicitly unlocked.

## Strategic Priorities
1. Reliability first: keep Cloud Run services and scheduler flows continuously healthy.
2. Risk first: hard-stop controls and allocation caps must always override autonomous actions.
3. Quality signals: only promote strategies with objective pass criteria.
4. Fast recovery: automate detection and rollback for runtime regressions.
5. Measurable learning: every incident produces an actionable entry in `LEARNINGS.md`.

## Tactical Queue
1. Maintain daily readiness checks and alerting.
2. Keep TradingView autonomy in strategy-gated mode with explicit limits.
3. Keep frontend read-only for control; Telegram remains the only agent command channel.
4. Keep SapphireTrade/Sapphire Alpha visuals data-native using live OHLC feeds from active venues.
5. Enforce frontend-to-alpha API contract checks before deploy (`frontend_contract_check.sh`).
6. Tighten deployment scripts around current service topology and remove stale deploy paths.
7. Publish weekly performance and stability summaries to Telegram.
