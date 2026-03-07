#!/usr/bin/env bash
set -euo pipefail

# Controlled strategy validation cycle:
#  1) Build weekly scorecard artifact.
#  2) Build promotion-gate artifacts for configured lanes.
#  3) Capture live strategy-ops decision snapshot from public API.
#
# Usage:
#   scripts/run_strategy_validation_cycle.sh
#
# Env:
#   PROJECT_ID (default sapphire-479610)
#   PLATFORM (default lighter)
#   SCORECARD_DAYS (default 7)
#   PROMOTION_CANDIDATES (default "overnight_ema_crossover@5m,overnight_ema_crossover_lite@5m")
#   BACKTEST_METRICS_DIR (optional; expects <strategy>@<timeframe>.json files)
#   STRATEGY_OPS_URL (default https://sapphirealpha.xyz/api/platform/strategy-ops)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
PLATFORM="${PLATFORM:-lighter}"
SCORECARD_DAYS="${SCORECARD_DAYS:-7}"
PROMOTION_CANDIDATES="${PROMOTION_CANDIDATES:-overnight_ema_crossover@5m,overnight_ema_crossover_lite@5m}"
BACKTEST_METRICS_DIR="${BACKTEST_METRICS_DIR:-}"
STRATEGY_OPS_URL="${STRATEGY_OPS_URL:-https://sapphirealpha.xyz/api/platform/strategy-ops}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${ROOT_DIR}/output/validation_cycles/${STAMP}"
GATES_DIR="${OUT_DIR}/promotion_gates"
mkdir -p "${OUT_DIR}" "${GATES_DIR}"

echo "[1/3] Building weekly scorecard..."
python3 "${ROOT_DIR}/scripts/run_weekly_strategy_scorecard.py" \
  --project "${PROJECT_ID}" \
  --platform "${PLATFORM}" \
  --days "${SCORECARD_DAYS}" \
  --output-json "${OUT_DIR}/weekly_scorecard.json" \
  --output-md "${OUT_DIR}/weekly_scorecard.md"

echo "[2/3] Building promotion gates..."
IFS=',' read -r -a CANDIDATES <<< "${PROMOTION_CANDIDATES}"
for lane in "${CANDIDATES[@]}"; do
  lane="$(echo "${lane}" | xargs)"
  [[ -z "${lane}" ]] && continue
  strategy="${lane%@*}"
  timeframe="${lane#*@}"
  if [[ -z "${strategy}" || -z "${timeframe}" || "${strategy}" == "${timeframe}" ]]; then
    echo "Skipping malformed candidate lane token: ${lane}" >&2
    continue
  fi

  gate_args=()
  if [[ -n "${BACKTEST_METRICS_DIR}" ]]; then
    candidate_json="${BACKTEST_METRICS_DIR}/${strategy}@${timeframe}.json"
    if [[ -f "${candidate_json}" ]]; then
      gate_args+=(--backtest-metrics-json "${candidate_json}")
    fi
  fi

  python3 "${ROOT_DIR}/scripts/run_strategy_promotion_gate.py" \
    --project "${PROJECT_ID}" \
    --platform "${PLATFORM}" \
    --strategy "${strategy}" \
    --timeframe "${timeframe}" \
    --output "${GATES_DIR}/${strategy}@${timeframe}.json" \
    "${gate_args[@]}"
done

echo "[3/3] Capturing strategy-ops decision snapshot..."
curl -fsS "${STRATEGY_OPS_URL}?days=${SCORECARD_DAYS}&refresh=true" > "${OUT_DIR}/strategy_ops_live.json"
python3 - "${OUT_DIR}/strategy_ops_live.json" "${OUT_DIR}/decision_summary.txt" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
payload = json.loads(src.read_text())
decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
assessment = payload.get("assessment", {}) if isinstance(payload.get("assessment"), dict) else {}
reasons = decision.get("reasons", []) if isinstance(decision.get("reasons"), list) else []

lines = [
    f"timestamp={payload.get('timestamp')}",
    f"window_days={payload.get('window_days')}",
    f"decision_label={decision.get('label')}",
    f"decision_go={decision.get('go')}",
    f"decision_source={decision.get('source')}",
    f"decision_diverged={decision.get('diverged')}",
    f"assessment_label={assessment.get('label')}",
    f"assessment_go={assessment.get('go')}",
    f"reason_count={len(reasons)}",
]
for idx, reason in enumerate(reasons[:5], start=1):
    lines.append(f"reason_{idx}={reason}")
dst.write_text("\n".join(lines) + "\n")
print("\n".join(lines))
PY

echo "✅ Validation cycle complete"
echo "Artifacts: ${OUT_DIR}"
