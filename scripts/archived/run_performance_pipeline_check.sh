#!/usr/bin/env bash
set -euo pipefail

DOMAIN_URL="${DOMAIN_URL:-https://sapphirealpha.xyz}"
API_USER="${API_USER:-sapphire}"
API_PASS="${API_PASS:-alpha2024}"
PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
POLL_SECONDS="${POLL_SECONDS:-45}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command '$1'" >&2
    exit 1
  }
}

require_cmd curl
require_cmd jq
require_cmd gcloud
require_cmd python3

AUTH=("${API_USER}:${API_PASS}")

echo "== Sapphire Performance Pipeline Check =="
echo "domain=${DOMAIN_URL}"
echo "project=${PROJECT_ID}"

baseline_json="$(curl -sS -u "${AUTH[0]}" "${DOMAIN_URL}/api/platform/metrics")"
baseline_total="$(echo "${baseline_json}" | jq -r '.trading.trades.total // 0')"
baseline_source="$(echo "${baseline_json}" | jq -r '.trading.source // "unknown"')"
echo "baseline_source=${baseline_source} baseline_trades_total=${baseline_total}"

trade_id="perf-check-$(date +%s)"
signal_id="perf-signal-$(date +%s)"
timestamp_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

message="$(python3 - <<PY
import json
print(json.dumps({
  "trade_id": "${trade_id}",
  "signal_id": "${signal_id}",
  "platform": "lighter",
  "symbol": "SOLUSDT",
  "side": "BUY",
  "success": True,
  "filled_quantity": 0.01,
  "avg_price": 100.0,
  "realized_pnl": 1.11,
  "fee": 0.01,
  "execution_time_ms": 80.0,
  "timestamp": "${timestamp_utc}",
  "metadata": {
    "source": "codex_performance_pipeline_check",
    "dry_run": True
  }
}))
PY
)"

echo "publishing synthetic trade-executed event..."
gcloud pubsub topics publish trade-executed \
  --project "${PROJECT_ID}" \
  --message "${message}" >/dev/null

updated_total=""
updated_source=""
for _ in $(seq 1 "${POLL_SECONDS}"); do
  metrics_json="$(curl -sS -u "${AUTH[0]}" "${DOMAIN_URL}/api/platform/metrics")"
  updated_total="$(echo "${metrics_json}" | jq -r '.trading.trades.total // 0')"
  updated_source="$(echo "${metrics_json}" | jq -r '.trading.source // "unknown"')"
  if [[ "${updated_total}" =~ ^[0-9]+$ ]] && [[ "${baseline_total}" =~ ^[0-9]+$ ]] && (( updated_total > baseline_total )); then
    break
  fi
  sleep 1
done

if [[ "${updated_total}" =~ ^[0-9]+$ ]] && [[ "${baseline_total}" =~ ^[0-9]+$ ]] && (( updated_total > baseline_total )); then
  echo "PASS: trading total incremented (${baseline_total} -> ${updated_total})"
else
  echo "FAIL: trading total did not increment within ${POLL_SECONDS}s" >&2
  exit 1
fi

logs_json="$(curl -sS -u "${AUTH[0]}" "${DOMAIN_URL}/api/platform/logs?limit=200")"
matching="$(echo "${logs_json}" | jq --arg sid "${signal_id}" '[.logs[] | select(.signal_id == $sid)] | length')"
if [[ "${matching}" != "0" ]]; then
  echo "PASS: execution log observed for signal_id=${signal_id}"
else
  echo "WARN: no log row found for signal_id=${signal_id} (metrics update still succeeded)"
fi

echo "final_source=${updated_source}"
echo "Performance pipeline check PASSED"
