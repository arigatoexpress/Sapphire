# LEARNINGS

## 2026-02-12

- Scope lock improves safety: keeping agents and automations on `arigatoexpress/Sapphire` only reduces accidental cross-repo divergence.
- Telegram heartbeat + command webhook is the highest-leverage human override path and must stay authenticated and monitored.
- Heartbeat replies are more usable when `/answer <response>` is supported as a first-class steering alias to `/steer`.
- Session-key approvals (`/approve` and `/reject`) reduce ambiguity during autonomous cycles and keep human control auditable.
- Frontend command inputs create unnecessary attack surface; web should stay telemetry/research only.
- `./scripts/autonomy_readiness_check.sh` is the canonical quick gate for cloud/runtime health across alpha, venue bots, gateway, and scheduler jobs.
- UI reliability depends on API contract parity: frontend-read endpoints (`/api/v2/platforms/status`, `/api/v2/trade/routing`, `/api/analytics/performance/stats`, `/logs/system`) must be kept live in `sapphire-alpha`.
- `./scripts/frontend_contract_check.sh` should run before web/control-plane deploys to catch UI-breaking API regressions.
- Strategy-gated TradingView autonomy (`TRADINGVIEW_ENFORCE_STRATEGY_RULES=true`) is required to keep autonomous actions bounded.
- OpenClaw dispatch should reject out-of-scope repo/project directives before execution to prevent cross-repo divergence.
- `./scripts/holistic_ops_check.sh` is the best single preflight command for focused operations readiness.
- `./scripts/gcp_scope_reconcile.sh --strict` must fail the pipeline if out-of-scope Cloud Run services or scheduler jobs reappear.
- Deprecated surfaces (`trading-dashboard-legacy`, `services/bot-retired_*`) should be removed to reduce operational entropy.
- Owner approval prompts are materially better when each autonomy session includes explicit why-now reasoning, expected outcome, benefit vs baseline, and deferral risk.
- Telegram digest compression should deduplicate repetitive AI updates while preserving decision-critical context for pending autonomy approvals.
- `skills/moltbook-interact` should be tracked as a first-class repo skill so external scout collaboration tooling is reproducible and auditable.

## Always Preserve

- Deterministic risk controls (`/kill`, `/resume`, venue allocation controls).
- Explicit secret checks before deploy.
- Idempotent scheduler + webhook workflows.
