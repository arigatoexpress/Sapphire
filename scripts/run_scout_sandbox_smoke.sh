#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${CI:-}" == "true" || "${SKIP_SOURCE_OF_TRUTH_CHECK:-0}" == "1" ]]; then
  echo "INFO: skipping source-of-truth check in CI/non-canonical runner context."
else
  "${ROOT_DIR}/scripts/check_source_of_truth.sh"
fi

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
SCOUT_SERVICE="${SCOUT_SERVICE:-sapphire-scout-sandbox}"
ALPHA_SERVICE="${ALPHA_SERVICE:-sapphire-alpha}"
SCOUT_TOKEN_SECRET="${SCOUT_TOKEN_SECRET:-SAPPHIRE_SCOUT_SANDBOX_TOKEN}"
SCRAPLING_SOURCE_URL="${SCRAPLING_SOURCE_URL:-https://news.ycombinator.com/}"
EXPECT_GTM_DISABLED="${EXPECT_GTM_DISABLED:-true}"

echo "== Scout Sandbox + Alpha Smoke =="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Scout:   ${SCOUT_SERVICE}"
echo "Alpha:   ${ALPHA_SERVICE}"

SCOUT_URL="$(gcloud run services describe "${SCOUT_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ALPHA_URL="$(gcloud run services describe "${ALPHA_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
SCOUT_TOKEN="$(gcloud secrets versions access latest --secret="${SCOUT_TOKEN_SECRET}" --project "${PROJECT_ID}")"

echo "Scout URL: ${SCOUT_URL}"
echo "Alpha URL: ${ALPHA_URL}"

echo "1) Scout health..."
SCOUT_HEALTH_RAW="$(curl -fsS "${SCOUT_URL}/health")"
python3 -c 'import json,sys; o=json.load(sys.stdin); print(json.dumps({"status":o.get("status"),"scrapling_enabled":o.get("scrapling_enabled"),"gtm_enabled":o.get("gtm_enabled"),"sandbox_token_configured":o.get("sandbox_token_configured")}, indent=2))' <<<"${SCOUT_HEALTH_RAW}"

echo "2) Scrapling collect..."
SCRAPLING_RAW="$(curl -fsS -X POST "${SCOUT_URL}/v1/intel/scrapling_collect" \
  -H "Authorization: Bearer ${SCOUT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"source_url\":\"${SCRAPLING_SOURCE_URL}\",\"selectors\":[\"title\",\"a.storylink,.titleline > a\"],\"limit_per_selector\":2,\"include_links\":true,\"max_links\":5}")"
python3 -c 'import json,sys; o=json.load(sys.stdin); print(json.dumps({"ok":o.get("ok"),"reason":o.get("reason"),"count":o.get("count"),"selector_hits":o.get("selector_hits")}, indent=2)); raise SystemExit(0 if o.get("ok") else 1)' <<<"${SCRAPLING_RAW}"

echo "3) GTM outbound guard..."
GTM_RAW="$(curl -fsS -X POST "${SCOUT_URL}/v1/gtm/outbound" \
  -H "Authorization: Bearer ${SCOUT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"outbound_payload":{"event":"smoke_test"},"external_url_hint":"https://app.clawgtm.com/api/v1/outbound"}')"
export GTM_RAW EXPECT_GTM_DISABLED
python3 - <<'PY'
import json
import os

expect_disabled = str(os.environ.get("EXPECT_GTM_DISABLED", "true")).lower() in {"1", "true", "yes", "on"}
obj = json.loads(os.environ["GTM_RAW"])
dispatch = obj.get("dispatch") or {}
reason = dispatch.get("reason")
print(json.dumps({"ok": obj.get("ok"), "reason": reason, "dispatched": dispatch.get("dispatched")}, indent=2))
if expect_disabled:
    raise SystemExit(0 if reason == "gtm_dispatch_disabled" else 1)
raise SystemExit(0)
PY

echo "4) Alpha intel feed status..."
ALPHA_INTEL_RAW="$(curl -fsS "${ALPHA_URL}/intel/feed?limit=5")"
python3 -c 'import json,sys; o=json.load(sys.stdin); st=o.get("status",{}); src=(st.get("sources") or {}).get("scrapling_web_intel") or {}; payload={"running":o.get("running"),"scrapling_intel_enabled":st.get("scrapling_intel_enabled"),"scrapling_status":src.get("status"),"scrapling_items":src.get("items"),"item_count":st.get("item_count"),"last_refresh_iso":st.get("last_refresh_iso")}; print(json.dumps(payload, indent=2)); ok=bool(st.get("scrapling_intel_enabled")) and src.get("status") in {"healthy","idle"}; raise SystemExit(0 if ok else 1)' <<<"${ALPHA_INTEL_RAW}"

echo "✅ Smoke PASSED"
