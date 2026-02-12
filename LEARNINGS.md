# LEARNINGS

## 2026-02-12

- Scope lock improves safety: keeping agents and automations on `arigatoexpress/Sapphire` only reduces accidental cross-repo divergence.
- Telegram heartbeat + command webhook is the highest-leverage human override path and must stay authenticated and monitored.
- Heartbeat replies are more usable when `/answer <response>` is supported as a first-class steering alias to `/steer`.
- Frontend command inputs create unnecessary attack surface; web should stay telemetry/research only.
- `./scripts/autonomy_readiness_check.sh` is the canonical quick gate for cloud/runtime health across alpha, venue bots, gateway, and scheduler jobs.
- UI reliability depends on API contract parity: frontend-read endpoints (`/api/v2/platforms/status`, `/api/v2/trade/routing`, `/api/analytics/performance/stats`, `/logs/system`) must be kept live in `sapphire-alpha`.
- `./scripts/frontend_contract_check.sh` should run before web/control-plane deploys to catch UI-breaking API regressions.
- Strategy-gated TradingView autonomy (`TRADINGVIEW_ENFORCE_STRATEGY_RULES=true`) is required to keep autonomous actions bounded.
- OpenClaw dispatch should reject out-of-scope repo/project directives before execution to prevent cross-repo divergence.
- Deprecated surfaces (`trading-dashboard-legacy`, `services/bot-retired_*`) should be removed to reduce operational entropy.

## Always Preserve

- Deterministic risk controls (`/kill`, `/resume`, venue allocation controls).
- Explicit secret checks before deploy.
- Idempotent scheduler + webhook workflows.
