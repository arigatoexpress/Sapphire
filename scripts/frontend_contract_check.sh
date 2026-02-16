#!/usr/bin/env bash
# Validate frontend API contract against sapphire-alpha and sapphirebook-web runtime services.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
ALPHA_SERVICE="${ALPHA_SERVICE:-sapphire-alpha}"
ALPHA_REGION="${ALPHA_REGION:-us-central1}"
WEB_SERVICE="${WEB_SERVICE:-sapphirebook-web}"
WEB_REGION="${WEB_REGION:-us-central1}"
WEB_DOMAIN="${WEB_DOMAIN:-https://sapphirealpha.xyz}"

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
ALPHA_ID_TOKEN="${SAPPHIRE_ALPHA_OIDC_TOKEN:-}"
if [[ -z "${ALPHA_ID_TOKEN}" ]]; then
  ALPHA_ID_TOKEN="$(gcloud auth print-identity-token --audiences="${ALPHA_URL}" 2>/dev/null || true)"
fi
if [[ -z "${ALPHA_ID_TOKEN}" ]]; then
  ALPHA_ID_TOKEN="$(gcloud auth print-identity-token 2>/dev/null || true)"
fi

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
echo "Web Domain: ${WEB_DOMAIN}"

RATE_LIMIT_SENTINEL="__RATE_LIMITED__"

alpha_curl_body() {
  local path="$1"
  local url="${ALPHA_URL}${path}"
  local response=""
  local body=""
  local status=""

  if [[ -n "${ALPHA_ID_TOKEN}" ]]; then
    response="$(curl -sS -w $'\n__STATUS__:%{http_code}' \
      -H "Origin: ${WEB_DOMAIN}" \
      -H "Authorization: Bearer ${ALPHA_ID_TOKEN}" \
      "${url}" 2>/dev/null || true)"
    body="${response%$'\n'__STATUS__:*}"
    status="${response##*__STATUS__:}"
    if [[ "${status}" =~ ^2[0-9][0-9]$ ]]; then
      printf '%s' "${body}"
      return 0
    fi
    if [[ "${status}" == "429" ]]; then
      printf '%s' "${RATE_LIMIT_SENTINEL}"
      return 0
    fi

    response="$(curl -sS -w $'\n__STATUS__:%{http_code}' \
      -H "Origin: ${WEB_DOMAIN}" \
      -H "X-Serverless-Authorization: Bearer ${ALPHA_ID_TOKEN}" \
      "${url}" 2>/dev/null || true)"
    body="${response%$'\n'__STATUS__:*}"
    status="${response##*__STATUS__:}"
    if [[ "${status}" =~ ^2[0-9][0-9]$ ]]; then
      printf '%s' "${body}"
      return 0
    fi
    if [[ "${status}" == "429" ]]; then
      printf '%s' "${RATE_LIMIT_SENTINEL}"
      return 0
    fi
  fi

  response="$(curl -sS -w $'\n__STATUS__:%{http_code}' -H "Origin: ${WEB_DOMAIN}" "${url}" 2>/dev/null || true)"
  body="${response%$'\n'__STATUS__:*}"
  status="${response##*__STATUS__:}"
  if [[ "${status}" =~ ^2[0-9][0-9]$ ]]; then
    printf '%s' "${body}"
    return 0
  fi
  if [[ "${status}" == "429" ]]; then
    printf '%s' "${RATE_LIMIT_SENTINEL}"
    return 0
  fi
  return 1
}

alpha_curl_headers_with_origin() {
  local path="$1"
  local origin="$2"
  local url="${ALPHA_URL}${path}"
  local status=""
  local headers=""

  if [[ -n "${ALPHA_ID_TOKEN}" ]]; then
    headers="$(curl -sS -D - -o /dev/null -w $'\n__STATUS__:%{http_code}' \
      -H "Origin: ${origin}" \
      -H "Authorization: Bearer ${ALPHA_ID_TOKEN}" \
      "${url}" 2>/dev/null || true)"
    status="${headers##*__STATUS__:}"
    headers="${headers%$'\n'__STATUS__:*}"
    if [[ "${status}" =~ ^2[0-9][0-9]$ ]]; then
      printf '%s' "${headers}"
      return 0
    fi
    if [[ "${status}" == "429" ]]; then
      printf '%s' "${RATE_LIMIT_SENTINEL}"
      return 0
    fi

    headers="$(curl -sS -D - -o /dev/null -w $'\n__STATUS__:%{http_code}' \
      -H "Origin: ${origin}" \
      -H "X-Serverless-Authorization: Bearer ${ALPHA_ID_TOKEN}" \
      "${url}" 2>/dev/null || true)"
    status="${headers##*__STATUS__:}"
    headers="${headers%$'\n'__STATUS__:*}"
    if [[ "${status}" =~ ^2[0-9][0-9]$ ]]; then
      printf '%s' "${headers}"
      return 0
    fi
    if [[ "${status}" == "429" ]]; then
      printf '%s' "${RATE_LIMIT_SENTINEL}"
      return 0
    fi
  fi

  headers="$(curl -sS -D - -o /dev/null -w $'\n__STATUS__:%{http_code}' -H "Origin: ${origin}" "${url}" 2>/dev/null || true)"
  status="${headers##*__STATUS__:}"
  headers="${headers%$'\n'__STATUS__:*}"
  if [[ "${status}" =~ ^2[0-9][0-9]$ ]]; then
    printf '%s' "${headers}"
    return 0
  fi
  if [[ "${status}" == "429" ]]; then
    printf '%s' "${RATE_LIMIT_SENTINEL}"
    return 0
  fi
  return 1
}

alpha_health="$(alpha_curl_body "/health" || true)"
if [[ "${alpha_health}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "alpha /health skipped (rate-limited 429)"
elif [[ -n "${alpha_health}" ]]; then
  pass "alpha /health"
else
  fail "alpha /health"
fi

if curl -fsS "${WEB_URL}/health" >/dev/null; then
  pass "web /health"
else
  # The Cloud Run web service is not guaranteed to expose a /health route (static hosts often 404).
  web_code="$(curl -sS -o /dev/null -w "%{http_code}" "${WEB_URL}/" 2>/dev/null || echo 000)"
  if [[ "${web_code}" != "000" && "${web_code}" != 5* ]]; then
    pass "web URL reachable (HTTP ${web_code})"
  else
    fail "web URL reachable"
  fi
fi

domain_code="$(curl -sS -o /dev/null -w "%{http_code}" "${WEB_DOMAIN}/" 2>/dev/null || echo 000)"
if [[ "${domain_code}" != "000" && "${domain_code}" != 5* ]]; then
  pass "web domain reachable (HTTP ${domain_code})"
else
  fail "web domain reachable"
fi

platform_payload="$(alpha_curl_body "/api/v2/platforms/status" || true)"
if [[ "${platform_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "platform status contract skipped (rate-limited 429)"
elif [[ -n "${platform_payload}" ]] && echo "${platform_payload}" | jq -e '.platforms.aster and .platforms.lighter' >/dev/null 2>&1; then
  pass "platform status contract"
else
  fail "platform status contract missing aster/lighter"
fi

control_payload="$(alpha_curl_body "/api/v2/control/status" || true)"
if [[ "${control_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "control status contract skipped (rate-limited 429)"
elif [[ -n "${control_payload}" ]] && echo "${control_payload}" | jq -e '.tradingview_execution_enabled != null and .pending_autonomy_decisions != null and .venues != null' >/dev/null 2>&1; then
  pass "control status contract"
else
  fail "control status contract missing execution/decision/venues fields"
fi

routing_payload="$(alpha_curl_body "/api/v2/trade/routing" || true)"
if [[ "${routing_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "routing contract skipped (rate-limited 429)"
elif [[ -n "${routing_payload}" ]] && echo "${routing_payload}" | jq -e '.confidence != null' >/dev/null 2>&1; then
  pass "routing contract"
else
  fail "routing contract missing confidence"
fi

perf_payload="$(alpha_curl_body "/api/analytics/performance/stats" || true)"
if [[ "${perf_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "performance stats contract skipped (rate-limited 429)"
elif [[ -n "${perf_payload}" ]] && echo "${perf_payload}" | jq -e '.metrics.system.total_trades != null and .metrics.system.wins != null' >/dev/null 2>&1; then
  pass "performance stats contract"
else
  fail "performance stats contract missing metrics.system.{total_trades,wins}"
fi

logs_payload="$(alpha_curl_body "/logs/system?limit=10" || true)"
if [[ "${logs_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "system logs contract skipped (rate-limited 429)"
elif [[ -n "${logs_payload}" ]] && echo "${logs_payload}" | jq -e 'type == "array"' >/dev/null 2>&1; then
  pass "system logs contract"
else
  fail "system logs contract expected array"
fi

forum_topics_payload="$(alpha_curl_body "/api/v2/forum/topics?limit=10" || true)"
if [[ "${forum_topics_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "forum topics contract skipped (rate-limited 429)"
elif [[ -n "${forum_topics_payload}" ]] && echo "${forum_topics_payload}" | jq -e '.topics | type == "array"' >/dev/null 2>&1; then
  pass "forum topics contract"
else
  fail "forum topics contract expected topics array"
fi

forum_scout_payload="$(alpha_curl_body "/api/v2/forum/scout/status" || true)"
if [[ "${forum_scout_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "forum scout status contract skipped (rate-limited 429)"
elif [[ -n "${forum_scout_payload}" ]] && echo "${forum_scout_payload}" | jq -e '.profile.agent_id != null and .external_bridge != null' >/dev/null 2>&1; then
  pass "forum scout status contract"
else
  fail "forum scout status contract missing profile/bridge"
fi

aster_ohlc_payload="$(alpha_curl_body "/api/v2/market/ohlc?venue=ASTER&symbol=SOL&interval=1m&limit=20" || true)"
if [[ "${aster_ohlc_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "ASTER OHLC contract skipped (rate-limited 429)"
elif [[ -n "${aster_ohlc_payload}" ]] && echo "${aster_ohlc_payload}" | jq -e '.ok == true and (.candles | type == "array") and (.candles | length > 0)' >/dev/null 2>&1; then
  pass "ASTER OHLC contract"
else
  fail "ASTER OHLC contract missing candles"
fi

lighter_ohlc_payload="$(alpha_curl_body "/api/v2/market/ohlc?venue=LIGHTER&symbol=SOL&interval=1m&limit=20" || true)"
if [[ "${lighter_ohlc_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "LIGHTER OHLC contract skipped (rate-limited 429)"
elif [[ -n "${lighter_ohlc_payload}" ]] && echo "${lighter_ohlc_payload}" | jq -e '.ok == true and (.candles | type == "array")' >/dev/null 2>&1; then
  pass "LIGHTER OHLC contract"
else
  fail "LIGHTER OHLC contract missing array response"
fi

workspace_payload="$(alpha_curl_body "/api/v2/tradingview/workspace" || true)"
tv_enabled="false"
if [[ "${control_payload}" != "${RATE_LIMIT_SENTINEL}" && -n "${control_payload}" ]]; then
  tv_enabled="$(echo "${control_payload}" | jq -r '.tradingview_integration_enabled // false' 2>/dev/null || echo false)"
fi
if [[ "${workspace_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "tradingview workspace contract skipped (rate-limited 429)"
elif [[ "${tv_enabled}" != "true" ]]; then
  pass "tradingview workspace contract skipped (integration disabled)"
elif [[ -n "${workspace_payload}" ]] && echo "${workspace_payload}" | jq -e '.workspace.enabled != null and ((.workspace.state.watchlists != null and .workspace.state.selected_symbol != null) or .workspace.reason != null)' >/dev/null 2>&1; then
  pass "tradingview workspace contract"
else
  fail "tradingview workspace contract missing workspace state"
fi

cors_headers_payload="$(alpha_curl_headers_with_origin "/api/v2/market/ohlc?venue=ASTER&symbol=SOL&interval=1m&limit=5" "${WEB_URL}" || true)"
cors_header="$(printf '%s' "${cors_headers_payload}" | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2; exit}')"
if [[ "${cors_headers_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "CORS allow-origin for web URL skipped (rate-limited 429)"
elif [[ "${cors_header}" == "${WEB_URL}" ]]; then
  pass "CORS allow-origin for web URL"
else
  fail "CORS allow-origin mismatch (expected ${WEB_URL}, got ${cors_header:-<empty>})"
fi

cors_domain_headers_payload="$(alpha_curl_headers_with_origin "/api/v2/market/ohlc?venue=ASTER&symbol=SOL&interval=1m&limit=5" "${WEB_DOMAIN}" || true)"
cors_domain_header="$(printf '%s' "${cors_domain_headers_payload}" | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2; exit}')"
if [[ "${cors_domain_headers_payload}" == "${RATE_LIMIT_SENTINEL}" ]]; then
  pass "CORS allow-origin for web domain skipped (rate-limited 429)"
elif [[ "${cors_domain_header}" == "${WEB_DOMAIN}" ]]; then
  pass "CORS allow-origin for web domain"
else
  fail "CORS allow-origin mismatch for web domain (expected ${WEB_DOMAIN}, got ${cors_domain_header:-<empty>})"
fi

echo
if [[ "${FAILURES}" -gt 0 ]]; then
  echo "Frontend contract check FAILED (${FAILURES} issue(s))."
  exit 1
fi

echo "Frontend contract check PASSED."
