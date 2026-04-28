#!/usr/bin/env bash
set -euo pipefail

# Weekly promotion pipeline job:
#  1) Build scorecard for all observed lanes.
#  2) Build promotion-gate artifacts for configured candidate lanes.
#
# Usage:
#   scripts/run_strategy_promotion_pipeline.sh
#
# Env:
#   PROJECT_ID (default sapphire-479610)
#   PLATFORM (default lighter)
#   SCORECARD_DAYS (default 7)
#   PROMOTION_CANDIDATES (default "overnight_ema_crossover@5m,overnight_ema_crossover_lite@5m")
#   BACKTEST_METRICS_DIR (optional path to backtest json files named <strategy>@<tf>.json)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
PLATFORM="${PLATFORM:-lighter}"
SCORECARD_DAYS="${SCORECARD_DAYS:-7}"
PROMOTION_CANDIDATES="${PROMOTION_CANDIDATES:-overnight_ema_crossover@5m,overnight_ema_crossover_lite@5m}"
BACKTEST_METRICS_DIR="${BACKTEST_METRICS_DIR:-}"

echo "[1/2] Weekly strategy scorecard..."
python3 "${ROOT_DIR}/scripts/run_weekly_strategy_scorecard.py" \
  --project "${PROJECT_ID}" \
  --platform "${PLATFORM}" \
  --days "${SCORECARD_DAYS}"

echo "[2/2] Promotion gates..."
IFS=',' read -r -a CANDIDATES <<< "${PROMOTION_CANDIDATES}"
for lane in "${CANDIDATES[@]}"; do
  lane="$(echo "${lane}" | xargs)"
  [[ -z "${lane}" ]] && continue
  strategy="${lane%@*}"
  timeframe="${lane#*@}"
  if [[ -z "${strategy}" || -z "${timeframe}" || "${strategy}" == "${timeframe}" ]]; then
    echo "Skipping malformed lane token: ${lane}" >&2
    continue
  fi
  backtest_arg=()
  if [[ -n "${BACKTEST_METRICS_DIR}" ]]; then
    candidate_json="${BACKTEST_METRICS_DIR}/${strategy}@${timeframe}.json"
    if [[ -f "${candidate_json}" ]]; then
      backtest_arg=(--backtest-metrics-json "${candidate_json}")
    fi
  fi
  python3 "${ROOT_DIR}/scripts/run_strategy_promotion_gate.py" \
    --project "${PROJECT_ID}" \
    --platform "${PLATFORM}" \
    --strategy "${strategy}" \
    --timeframe "${timeframe}" \
    "${backtest_arg[@]}"
done

echo "✅ Promotion pipeline artifacts generated."
