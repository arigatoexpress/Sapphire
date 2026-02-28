#!/usr/bin/env bash
set -euo pipefail

DOMAIN_URL="${DOMAIN_URL:-https://sapphirealpha.xyz}"
API_USER="${API_USER:-sapphire}"
API_PASS="${API_PASS:-alpha2024}"
WINDOWS_WEBHOOK_URL="${WINDOWS_WEBHOOK_URL:-http://100.71.10.48:9090}"
TEST_SYMBOL="${TEST_SYMBOL:-SOLUSDT}"
TEST_ACTION="${TEST_ACTION:-buy}"
POLL_SECONDS="${POLL_SECONDS:-30}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command '$1'" >&2
    exit 1
  }
}

require_cmd curl
require_cmd jq
require_cmd python3

pass() { printf "PASS: %s\n" "$1"; }
fail() { printf "FAIL: %s\n" "$1" >&2; }

echo "== Sapphire E2E Signal Validation =="
echo "domain=${DOMAIN_URL}"
echo "webhook=${WINDOWS_WEBHOOK_URL}"

# 1) Platform readiness
readiness_json="$(curl -sS -u "${API_USER}:${API_PASS}" "${DOMAIN_URL}/api/platform/readiness")"
overall_ok="$(echo "$readiness_json" | jq -r '.overall_ok // false')"
if [[ "$overall_ok" == "true" ]]; then
  pass "platform readiness overall_ok=true"
else
  fail "platform readiness not OK"
  echo "$readiness_json" | jq -C .
  exit 1
fi

# 2) Windows endpoints
webhook_health_code="$(curl -sS -o /tmp/sapphire_webhook_health.json -w '%{http_code}' "${WINDOWS_WEBHOOK_URL}/webhook/health")"
if [[ "$webhook_health_code" == "200" ]]; then
  pass "windows webhook health 200"
else
  fail "windows webhook health status=${webhook_health_code}"
  cat /tmp/sapphire_webhook_health.json || true
  exit 1
fi

tv_health_code="$(curl -sS -o /tmp/sapphire_tv_health.json -w '%{http_code}' "http://100.71.10.48:8081/health" || true)"
if [[ "$tv_health_code" == "200" ]]; then
  pass "windows tv-agent health 200"
else
  fail "windows tv-agent health status=${tv_health_code:-none}"
  cat /tmp/sapphire_tv_health.json || true
  exit 1
fi

# 3) Publish test signal
msg_tag="codex_e2e_$(date +%s)"
now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
payload="$(python3 - <<PY
import json
print(json.dumps({
  "symbol": "${TEST_SYMBOL}",
  "action": "${TEST_ACTION}",
  "price": "82.40",
  "time": "${now_utc}",
  "message": "${msg_tag}",
  "confidence": 0.9,
  "z_score": -2.1,
}))
PY
)"

signal_resp="$(curl -sS -X POST "${WINDOWS_WEBHOOK_URL}/webhook/tradingview" -H 'Content-Type: application/json' -d "$payload")"
published="$(echo "$signal_resp" | jq -r '.publish.published // false')"
signal_id="$(echo "$signal_resp" | jq -r '.signal_id // empty')"
if [[ "$published" == "true" && -n "$signal_id" ]]; then
  pass "test signal published to pubsub (signal_id=${signal_id})"
else
  fail "signal publish failed"
  echo "$signal_resp" | jq -C . || echo "$signal_resp"
  exit 1
fi

# 4) Verify signal is visible in platform logs
found="false"
for _ in $(seq 1 "$POLL_SECONDS"); do
  logs_json="$(curl -sS -u "${API_USER}:${API_PASS}" "${DOMAIN_URL}/api/platform/logs?limit=50")"
  hit_count="$(echo "$logs_json" | jq --arg sid "$signal_id" '[.logs[] | select(.signal_id == $sid)] | length')"
  if [[ "$hit_count" != "0" ]]; then
    found="true"
    break
  fi
  sleep 1
done

if [[ "$found" == "true" ]]; then
  pass "signal observed in platform logs"
else
  fail "signal not observed in platform logs within ${POLL_SECONDS}s"
  exit 1
fi

# 5) Final platform metrics snapshot
metrics_json="$(curl -sS -u "${API_USER}:${API_PASS}" "${DOMAIN_URL}/api/platform/metrics")"
echo "-- Final Health --"
echo "$metrics_json" | jq -c '.health'

echo
echo "E2E validation PASSED"
