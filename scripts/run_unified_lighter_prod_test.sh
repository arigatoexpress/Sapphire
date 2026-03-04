#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
GATEWAY_SERVICE="${GATEWAY_SERVICE:-sapphire-gateway}"
LIGHTER_HOST="${LIGHTER_HOST:-rari@100.87.225.89}"
LIGHTER_SERVICE="${LIGHTER_SERVICE:-lighter-trading}"
WEBHOOK_SECRET_NAME="${WEBHOOK_SECRET_NAME:-SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET}"

SYMBOL="${SYMBOL:-SOLUSDT}"
ACTION="${ACTION:-buy}"
QUANTITY="${QUANTITY:-0.01}"
CONFIDENCE="${CONFIDENCE:-0.89}"
STRATEGY="${STRATEGY:-luxalgo_msb_ob}"
TIMEFRAME="${TIMEFRAME:-5m}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command '$1'" >&2
    exit 1
  }
}

for cmd in gcloud curl jq ssh python3; do
  require_cmd "$cmd"
done

pass() { printf "PASS: %s\n" "$1"; }
fail() { printf "FAIL: %s\n" "$1" >&2; }

echo "== Unified Lighter Production Test =="
echo "project=${PROJECT_ID} region=${REGION} gateway_service=${GATEWAY_SERVICE}"
echo "lighter_host=${LIGHTER_HOST} lighter_service=${LIGHTER_SERVICE}"
echo "signal=${ACTION} ${SYMBOL} qty=${QUANTITY} strategy=${STRATEGY} tf=${TIMEFRAME}"
echo

echo "[1/7] Resolve gateway URL"
GATEWAY_URL="$(gcloud run services describe "${GATEWAY_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.url)')"
if [[ -z "${GATEWAY_URL:-}" ]]; then
  fail "could not resolve gateway URL"
  exit 1
fi
pass "gateway_url=${GATEWAY_URL}"

echo
echo "[2/7] Gateway ingress health"
gateway_health_code="$(curl -sS -o /tmp/sapphire_gateway_webhook_health.json -w '%{http_code}' "${GATEWAY_URL}/webhook/health")"
if [[ "${gateway_health_code}" != "200" ]]; then
  fail "gateway webhook health status=${gateway_health_code}"
  cat /tmp/sapphire_gateway_webhook_health.json || true
  exit 1
fi
pass "gateway webhook health 200"

echo
echo "[3/7] rari2 lighter service health"
lighter_state="$(ssh -o BatchMode=yes -o ConnectTimeout=10 "${LIGHTER_HOST}" "systemctl is-active ${LIGHTER_SERVICE}" || true)"
if [[ "${lighter_state}" != "active" ]]; then
  fail "lighter service not active (${lighter_state})"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${LIGHTER_HOST}" "systemctl show ${LIGHTER_SERVICE} -p ActiveState -p SubState -p MainPID" || true
  exit 1
fi
pass "lighter service active"

echo
echo "[4/7] Load TradingView webhook secret"
WEBHOOK_SECRET="$(gcloud secrets versions access latest \
  --secret="${WEBHOOK_SECRET_NAME}" \
  --project="${PROJECT_ID}" 2>/dev/null | tr -d '\r\n')"
if [[ -z "${WEBHOOK_SECRET}" ]]; then
  fail "webhook secret is empty (${WEBHOOK_SECRET_NAME})"
  exit 1
fi
pass "webhook secret loaded"

now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
start_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
signal_payload="$(python3 - <<PY
import json, uuid
print(json.dumps({
  "symbol": "${SYMBOL}",
  "action": "${ACTION}",
  "quantity": float("${QUANTITY}"),
  "confidence": float("${CONFIDENCE}"),
  "price": 0,
  "time": "${now_utc}",
  "source": "codex-unified-prod-test",
  "message": f"unified_prod_test_{uuid.uuid4().hex[:10]}",
  "metadata": {
    "strategy": "${STRATEGY}",
    "timeframe": "${TIMEFRAME}",
    "reason": "Unified production canary validation",
    "origin": "run_unified_lighter_prod_test.sh"
  }
}, separators=(",", ":")))
PY
)"

echo
echo "[5/7] Publish gateway canary"
publish_resp="$(curl -sS -X POST "${GATEWAY_URL}/webhook/tradingview" \
  -H "Content-Type: application/json" \
  -H "X-Sapphire-Webhook-Secret: ${WEBHOOK_SECRET}" \
  -d "${signal_payload}")"
echo "${publish_resp}" | jq -C . || echo "${publish_resp}"

signal_id="$(echo "${publish_resp}" | jq -r '.signal_id // empty')"
publish_status="$(echo "${publish_resp}" | jq -r '.status // empty')"
if [[ -z "${signal_id}" ]]; then
  fail "no signal_id returned from gateway"
  exit 1
fi
if [[ "${publish_status}" != "published" && "${publish_status}" != "duplicate_ignored" ]]; then
  fail "unexpected gateway status='${publish_status}'"
  exit 1
fi
pass "gateway accepted signal_id=${signal_id} status=${publish_status}"

echo
echo "[6/7] Verify gateway ingress + lighter processing"
found_gateway="false"
found_lighter="false"
exec_line=""
for _ in $(seq 1 "${WAIT_SECONDS}"); do
  status_json="$(curl -sS "${GATEWAY_URL}/webhook/tradingview/status?limit=40" || true)"
  if echo "${status_json}" | jq -e --arg sid "${signal_id}" '.recent[]? | select(.signal_id == $sid)' >/dev/null 2>&1; then
    found_gateway="true"
  fi

  if ssh -o BatchMode=yes -o ConnectTimeout=8 "${LIGHTER_HOST}" \
      "sudo journalctl -u ${LIGHTER_SERVICE} --since '${start_iso}' --no-pager | grep -F '${signal_id}'" >/tmp/lighter_signal_hit.txt 2>/dev/null; then
    found_lighter="true"
    exec_line="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "${LIGHTER_HOST}" \
      "sudo journalctl -u ${LIGHTER_SERVICE} --since '${start_iso}' --no-pager | grep -F 'Execution verify | signal=${signal_id}' | tail -n 1" || true)"
  fi

  if [[ "${found_gateway}" == "true" && "${found_lighter}" == "true" ]]; then
    break
  fi
  sleep 1
done

if [[ "${found_gateway}" == "true" ]]; then
  pass "gateway status feed contains signal_id"
else
  fail "gateway status feed missing signal_id after ${WAIT_SECONDS}s"
  exit 1
fi

if [[ "${found_lighter}" == "true" ]]; then
  pass "lighter logs contain signal_id"
  if [[ -n "${exec_line}" ]]; then
    echo "execution_line=${exec_line}"
  fi
else
  fail "lighter logs missing signal_id after ${WAIT_SECONDS}s"
  ssh -o BatchMode=yes -o ConnectTimeout=8 "${LIGHTER_HOST}" "sudo journalctl -u ${LIGHTER_SERVICE} -n 120 --no-pager" || true
  exit 1
fi

echo
echo "[7/7] Firestore execution verification"
python3 - <<PY
from google.cloud import firestore

project = "${PROJECT_ID}"
signal_id = "${signal_id}"
client = firestore.Client(project=project)

row = None
doc_ids = [
    f"lighter_{signal_id}_signal",
    f"lighter_{signal_id}_hub",
]
for doc_id in doc_ids:
    snap = client.collection("execution_verifications").document(doc_id).get()
    if snap.exists:
        row = snap.to_dict() or {}
        break

if row is None:
    # Fallback to single-field filter (built-in index) if direct ids not present.
    candidates = list(
        client.collection("execution_verifications")
        .where("signal_id", "==", signal_id)
        .limit(5)
        .stream()
    )
    if candidates:
        row = candidates[-1].to_dict() or {}

if row is None:
    raise SystemExit("FAIL: execution_verifications has no row for signal")

print("PASS: execution_verifications row found")
print("  success=", row.get("success"))
print("  symbol=", row.get("symbol"))
print("  side=", row.get("side"))
print("  strategy=", row.get("strategy"))
print("  timeframe=", row.get("timeframe"))
print("  filled_quantity=", row.get("filled_quantity"))
print("  avg_price=", row.get("avg_price"))
print("  error_message=", row.get("error_message"))
PY

echo
echo "Unified lighter production test PASSED."
echo "signal_id=${signal_id}"
