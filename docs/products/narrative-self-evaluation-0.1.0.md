# Narrative Self-Evaluation 0.1.0

Narrative Self-Evaluation closes the loop on Sapphire narrative theses without adding any live model or trading behavior. It scores `NarrativeThesis` rows against local realized outcomes after configured horizons and turns the results into aggregate diagnostics.

## Scope

- Pure scorer in `lib/narrative_evaluation`.
- Idempotent service in `services/narrative_evaluation`.
- Stdin JSON tool `narrative_eval`.
- Dashboard page `/narrative-eval`.
- APIs `/api/narrative-eval-summary` and `/api/narrative-eval-aggregates`.

## Safety

- Dry-run by construction.
- No live LLM calls.
- No Telegram sends.
- No order placement, position sizing, or trading critical-path edits.
- Generated score artifacts include provenance sidecars.
- Missing outcomes are reported as `pending_horizon` or `no_outcome`; they are not counted as wins.

## Scoring Contract

Each score row covers one thesis and one horizon. The scorer records:

- `implied_position` and derived predicted direction.
- Actual return percent and derived actual direction.
- `correct`, `false_positive`, calibration error, and Brier score.
- Grouping dimensions: symbol, timeframe, edge bucket, source mix, and regime.
- Diagnostics such as `false_positive_directional_thesis`, `overconfident_miss`, and `missed_directional_move`.

The service writes append-only rows under `data/narrative_evaluation/<YYYY-MM-DD>/scores.jsonl` and avoids duplicate `score_id` writes.

## Inputs

The service reads narrative rows from `data/narratives/**/theses.jsonl` and local outcome rows from:

- `data/narrative_evaluation/outcomes.jsonl`
- `data/signals/**/*.jsonl`
- `data/performance/signals.jsonl`

Outcome rows may provide `actual_return_pct`, `return_pct`, `pnl_pct`, or `move_pct`. Rows with entry/exit prices can also be converted into a return percent.

## Dashboard

The dashboard exposes scored counts, accuracy, false-positive rate, calibration error, aggregate buckets, recent scores, and honest unscored diagnostics.
