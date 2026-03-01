# Autonomy Lab Contract (2026-03-01)

## Objective
Expose a production-safe, read-only autonomy + learning + experimentation surface on the public platform.

## Canonical endpoint
- `GET /api/platform/autonomy`

## Response shape
- `overall_ok`: boolean (readiness posture)
- `autonomy`: control-plane state
  - `full_autonomy_enabled`
  - `owner_approval_required`
  - `dex_execution_stage`
  - `dex_live_dispatch_enabled`
  - `tradingview_execution_enabled`
  - `autonomy_dispatch_count`
  - `pending_autonomy_decisions`
  - `failure_pressure`
- `learning`: self-learning telemetry
  - `memory_enabled`, `memory_stats`
  - `cognition_enabled`, `cognition_metrics`
  - `alpha_scanner`, `grid_trader`
- `risk`: guardrail status
  - `readiness_ok`
  - `readiness_blockers`
  - `dispatcher_hardening`
  - `routing_confidence`
- `experiments`: generated safe backlog (advisory only)
  - `title`, `lane`, `priority`, `hypothesis`, `success_metric`, `safety`, `next_step`, `source`
- `sources`: source-level health/latency for all upstream dependencies
- `readiness`: summarized gate status

## Data sources
- Alpha control: `/control/status`
- Alpha routing: `/routing`
- Alpha performance: `/performance/stats`
- Alpha scout status: `/forum/scout/status`
- Platform readiness: internal `/_build_readiness_payload`
- Intel: internal `/_fetch_intel_feed_payload`
- Monitor: Firestore `system_status/current`

## Safety model
- Public web remains read-only.
- Experiment backlog is recommendation-only and sandbox-first.
- No endpoint in this contract mutates trading execution, infra, or model policy.

## UI route
- `/autonomy` (Autonomy Lab)
