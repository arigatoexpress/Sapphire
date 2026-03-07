# System Status Summary — 2026-03-07

## Scope completed

- Bot execution policy hardening (`services/bot-lighter/src/main.py`)
- Strategy validation artifact pipeline run
- Scheduler cleanup (deprecated paused jobs deleted)
- Production verification run

## Live posture

- Public platform: `https://sapphirealpha.xyz`
- Readiness: `overall_ok=true` (contracts `19/19`, cloud `6/6`, edge critical `2/2`)
- Signal ingress gate: healthy (`gateway ingress enabled/publishing`)
- Public mutation route remains closed (`/jobs/superswarm/hourly-rollup` = `404`)

## Lighter runtime state

### rari2 (live lane)

- `lighter-trading`: active
- New runtime controls active:
  - `LIGHTER_GO_NOGO_GATE_ENABLED=true`
  - platform decision gate enabled (`LIGHTER_PLATFORM_DECISION_GATE_ENABLED=true`)
  - reject-tax trend deltas (1h/6h/24h) in Telegram digest/heartbeat
- Entry gate now blocks when GO/NO-GO is NO-GO with explicit reason.
- Current blocking signals observed in logs:
  - `go_no_go_block: reject_tax 77.2% > 75.0% (n=442)`
  - risk kernel hold when daily loss threshold is breached

### rari1 (paper/monitor lane)

- `lighter-trading`: active
- DNS/connectivity instability to Lighter remains expected on this lane.
- Policy and telemetry code is synced with rari2.

## Validation artifacts generated

Path:

- `output/validation_cycles/20260307T234341Z`

Contents:

- `weekly_scorecard.json`
- `weekly_scorecard.md`
- `promotion_gates/overnight_ema_crossover@5m.json`
- `promotion_gates/overnight_ema_crossover_lite@5m.json`
- `strategy_ops_live.json`
- `decision_summary.txt`

Observed decision:

- `decision_label=NO-GO`
- `decision_source=operator_brief`
- `assessment_label=GO`
- blocker: `data_quality degraded: execution_outcomes`

## Deprecated/pruned items

Deleted paused, deprecated scheduler jobs in `sapphire-479610`:

- `sapphire-promotion-hourly-run`
- `sapphire-health-check`
- `sapphire-events-ledger-sync-5m`
- `sapphire-scorecard-hourly-run`
- `sapphire-backfill-hourly-run`

Current scheduler inventory now contains only active canonical jobs.

## Repo hygiene updates

- Added `scripts/run_strategy_validation_cycle.sh` (controlled analysis-only cycle)
- Updated `scripts/run_weekly_strategy_scorecard.py` fallback paths to avoid index hard-fail
- Updated `scripts/run_strategy_promotion_gate.py` fallback paths to avoid index hard-fail
- Updated `.gitignore` to suppress local environment/output churn:
  - `.venv-backtest`
  - `output/`
- Updated `docs/STRATEGY_PROMOTION_PIPELINE.md` with controlled validation workflow + gate envs

## Remaining hard blockers

1. Strategy ops final decision remains NO-GO due data-quality degradation.
2. Live lane reject-tax is above threshold, so the new gate is intentionally suppressing entries.
3. Hard risk kernel can still hold entries after loss threshold breaches.

These are expected safety stops, not runtime failures.
