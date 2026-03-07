# Strategy Promotion Pipeline

Canonical stage path:

1. `backtest`
2. `paper`
3. `capped_live`
4. `scale`

## Artifacts

- Promotion gate artifact (per lane):
  - `scripts/run_strategy_promotion_gate.py`
  - Output: `output/promotion_gates/<strategy>_<timeframe>_<timestamp>.json`
- Weekly scorecard:
  - `scripts/run_weekly_strategy_scorecard.py`
  - Output:
    - `output/strategy_scorecards/weekly_<platform>_<yyyymmdd>.json`
    - `output/strategy_scorecards/weekly_<platform>_<yyyymmdd>.md`
- Weekly pipeline wrapper:
  - `scripts/run_strategy_promotion_pipeline.sh`
- Controlled validation cycle wrapper:
  - `scripts/run_strategy_validation_cycle.sh`
  - Output:
    - `output/validation_cycles/<timestamp>/weekly_scorecard.json`
    - `output/validation_cycles/<timestamp>/promotion_gates/*.json`
    - `output/validation_cycles/<timestamp>/strategy_ops_live.json`
    - `output/validation_cycles/<timestamp>/decision_summary.txt`

## One-shot run

```bash
python3 scripts/run_strategy_promotion_gate.py \
  --project sapphire-479610 \
  --platform lighter \
  --strategy overnight_ema_crossover \
  --timeframe 5m
```

```bash
python3 scripts/run_weekly_strategy_scorecard.py \
  --project sapphire-479610 \
  --platform lighter \
  --days 7
```

## Weekly job runner

```bash
PROJECT_ID=sapphire-479610 \
PLATFORM=lighter \
PROMOTION_CANDIDATES="overnight_ema_crossover@5m,overnight_ema_crossover_lite@5m" \
bash scripts/run_strategy_promotion_pipeline.sh
```

## Controlled validation run (recommended)

```bash
PROJECT_ID=sapphire-479610 \
PLATFORM=lighter \
SCORECARD_DAYS=7 \
PROMOTION_CANDIDATES="overnight_ema_crossover@5m,overnight_ema_crossover_lite@5m" \
bash scripts/run_strategy_validation_cycle.sh
```

This run intentionally stays analysis-only. It generates deterministic artifacts
without changing live trading policy.

## Execution safety integration

- Bot-side live entry gate is controlled by:
  - `LIGHTER_GO_NOGO_GATE_ENABLED` (default `true`)
  - `LIGHTER_GO_NOGO_CACHE_TTL_SECONDS` (default `20`)
- Gate posture is computed from:
  - sync freshness + failsafe/jurisdiction/risk kernel blocks
  - reject-tax and hard-fail thresholds
- Reject-tax trend deltas (1h/6h/24h) are included in Telegram digest/heartbeat
  to expose directionality, not just point-in-time values.

## Gate semantics (summary)

- `backtest -> paper`: requires minimum backtest sample, expectancy, and max drawdown pass.
- `paper -> capped_live`: requires sufficient paper sample, bounded reject-tax/hard-fail, and minimum fill-success.
- `capped_live -> scale`: requires minimum live sample, positive realized PnL threshold, bounded reject-tax/hard-fail, and bounded equity drawdown.

The artifact always emits explicit fail reasons, so promotion decisions are machine-auditable.
