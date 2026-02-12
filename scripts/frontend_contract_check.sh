#!/usr/bin/env bash
# Validate frontend API contract against sapphire-alpha and sapphirebook-web runtime services.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
ALPHA_SERVICE="${ALPHA_SERVICE:-sapphire-alpha}"
ALPHA_REGION="${ALPHA_REGION:-us-central1}"
WEB_SERVICE="${WEB_SERVICE:-sapphirebook-web}"
WEB_REGION="${WEB_REGION:-us-central1}"

FAILURES=0

pass() {
  echo "PASS: $1"
}

fail() {
  echo "FAIL: $1"
  FAILURES=$((FAILURES + 1))
}

need_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command available: $cmd"
  else
    fail "missing command: $cmd"
  fi
}

need_cmd gcloud
need_cmd jq
need_cmd curl

ALPHA_URL="$(gcloud run services describe "${ALPHA_SERVICE}" --project "${PROJECT_ID}" --region "${ALPHA_REGION}" --format='value(status.url)')"
WEB_URL="$(gcloud run services describe "${WEB_SERVICE}" --project "${PROJECT_ID}" --region "${WEB_REGION}" --format='value(status.url)')"

if [[ -z "${ALPHA_URL}" ]]; then
  fail "could not resolve alpha URL"
  exit 1
fi
if [[ -z "${WEB_URL}" ]]; then
  fail "could not resolve web URL"
  exit 1
fi

echo "== Frontend Contract Check =="
echo "Alpha URL: ${ALPHA_URL}"
echo "Web URL: ${WEB_URL}"

if curl -fsS "${ALPHA_URL}/health" >/dev/null; then
  pass "alpha /health"
else
  fail "alpha /health"
fi

if curl -fsS "${WEB_URL}/health" >/dev/null; then
  pass "web /health"
else
  fail "web /health"
fi

platform_payload="$(curl -fsS "${ALPHA_URL}/api/v2/platforms/status" || true)"
if [[ -n "${platform_payload}" ]] && echo "${platform_payload}" | jq -e '.platforms.aster and .platforms.lighter' >/dev/null 2>&1; then
  pass "platform status contract"
else
  fail "platform status contract missing aster/lighter"
fi

control_payload="$(curl -fsS "${ALPHA_URL}/api/v2/control/status" || true)"
if [[ -n "${control_payload}" ]] && echo "${control_payload}" | jq -e '.tradingview_execution_enabled != null and .pending_autonomy_decisions != null and .venues != null' >/dev/null 2>&1; then
  pass "control status contract"
else
  fail "control status contract missing execution/decision/venues fields"
fi

routing_payload="$(curl -fsS "${ALPHA_URL}/api/v2/trade/routing" || true)"
if [[ -n "${routing_payload}" ]] && echo "${routing_payload}" | jq -e '.confidence != null' >/dev/null 2>&1; then
  pass "routing contract"
else
  fail "routing contract missing confidence"
fi

perf_payload="$(curl -fsS "${ALPHA_URL}/api/analytics/performance/stats" || true)"
if [[ -n "${perf_payload}" ]] && echo "${perf_payload}" | jq -e '.metrics.system.total_trades != null and .metrics.system.wins != null' >/dev/null 2>&1; then
  pass "performance stats contract"
else
  fail "performance stats contract missing metrics.system.{total_trades,wins}"
fi

logs_payload="$(curl -fsS "${ALPHA_URL}/logs/system?limit=10" || true)"
if [[ -n "${logs_payload}" ]] && echo "${logs_payload}" | jq -e 'type == "array"' >/dev/null 2>&1; then
  pass "system logs contract"
else
  fail "system logs contract expected array"
fi

forum_topics_payload="$(curl -fsS "${ALPHA_URL}/api/v2/forum/topics?limit=10" || true)"
if [[ -n "${forum_topics_payload}" ]] && echo "${forum_topics_payload}" | jq -e '.topics | type == "array"' >/dev/null 2>&1; then
  pass "forum topics contract"
else
  fail "forum topics contract expected topics array"
fi

forum_scout_payload="$(curl -fsS "${ALPHA_URL}/api/v2/forum/scout/status" || true)"
if [[ -n "${forum_scout_payload}" ]] && echo "${forum_scout_payload}" | jq -e '.profile.agent_id != null and .external_bridge != null' >/dev/null 2>&1; then
  pass "forum scout status contract"
else
  fail "forum scout status contract missing profile/bridge"
fi

aster_ohlc_payload="$(curl -fsS "${ALPHA_URL}/api/v2/market/ohlc?venue=ASTER&symbol=SOL&interval=1m&limit=20" || true)"
if [[ -n "${aster_ohlc_payload}" ]] && echo "${aster_ohlc_payload}" | jq -e '.ok == true and (.candles | type == "array") and (.candles | length > 0)' >/dev/null 2>&1; then
  pass "ASTER OHLC contract"
else
  fail "ASTER OHLC contract missing candles"
fi

lighter_ohlc_payload="$(curl -fsS "${ALPHA_URL}/api/v2/market/ohlc?venue=LIGHTER&symbol=SOL&interval=1m&limit=20" || true)"
if [[ -n "${lighter_ohlc_payload}" ]] && echo "${lighter_ohlc_payload}" | jq -e '.ok == true and (.candles | type == "array")' >/dev/null 2>&1; then
  pass "LIGHTER OHLC contract"
else
  fail "LIGHTER OHLC contract missing array response"
fi

workspace_payload="$(curl -fsS "${ALPHA_URL}/api/v2/tradingview/workspace" || true)"
if [[ -n "${workspace_payload}" ]] && echo "${workspace_payload}" | jq -e '.workspace.state.watchlists != null and .workspace.state.selected_symbol != null' >/dev/null 2>&1; then
  pass "tradingview workspace contract"
else
  fail "tradingview workspace contract missing workspace state"
fi

cors_header="$(curl -si -H "Origin: ${WEB_URL}" "${ALPHA_URL}/api/v2/market/ohlc?venue=ASTER&symbol=SOL&interval=1m&limit=5" | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2; exit}')"
if [[ "${cors_header}" == "${WEB_URL}" ]]; then
  pass "CORS allow-origin for web URL"
else
  fail "CORS allow-origin mismatch (expected ${WEB_URL}, got ${cors_header:-<empty>})"
fi

echo
if [[ "${FAILURES}" -gt 0 ]]; then
  echo "Frontend contract check FAILED (${FAILURES} issue(s))."
  exit 1
fi

echo "Frontend contract check PASSED."
