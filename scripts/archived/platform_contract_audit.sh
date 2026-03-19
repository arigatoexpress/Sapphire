#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-https://sapphirealpha.xyz}"
AUTH_USER="${AUTH_USER:-sapphire}"
AUTH_PASS="${AUTH_PASS:-alpha2024}"
AUTH="${AUTH_USER}:${AUTH_PASS}"
CURL_RETRIES="${CURL_RETRIES:-4}"
CURL_RETRY_DELAY_SEC="${CURL_RETRY_DELAY_SEC:-1}"

FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

need_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "command available: $1"
  else
    fail "missing command: $1"
  fi
}

need_cmd curl
need_cmd jq

fetch_body() {
  local url="$1"
  local body=""
  local attempt=1
  while [[ "$attempt" -le "$CURL_RETRIES" ]]; do
    body="$(curl -sS -u "$AUTH" "$url" || true)"
    if [[ -n "$body" ]]; then
      printf "%s" "$body"
      return 0
    fi
    sleep "$CURL_RETRY_DELAY_SEC"
    attempt=$((attempt + 1))
  done
  return 1
}

fetch_headers() {
  local url="$1"
  local headers=""
  local attempt=1
  while [[ "$attempt" -le "$CURL_RETRIES" ]]; do
    headers="$(curl -sSI -u "$AUTH" "$url" || true)"
    if echo "$headers" | grep -q '^HTTP/'; then
      printf "%s" "$headers"
      return 0
    fi
    sleep "$CURL_RETRY_DELAY_SEC"
    attempt=$((attempt + 1))
  done
  return 1
}

fetch_code() {
  local url="$1"
  local code=""
  local attempt=1
  while [[ "$attempt" -le "$CURL_RETRIES" ]]; do
    code="$(curl -sS -u "$AUTH" -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" != "000" && "$code" != "" ]]; then
      printf "%s" "$code"
      return 0
    fi
    sleep "$CURL_RETRY_DELAY_SEC"
    attempt=$((attempt + 1))
  done
  printf "000"
  return 1
}

manifest="$(fetch_body "$DOMAIN/api/platform/contracts" || true)"
if [[ -z "${manifest}" ]]; then
  fail "unable to fetch /api/platform/contracts"
  exit 1
fi

if ! echo "$manifest" | jq -e '.version and (.endpoints | type == "array")' >/dev/null 2>&1; then
  fail "invalid contract manifest payload"
  echo "$manifest" | jq . 2>/dev/null || true
  exit 1
fi

contract_version="$(echo "$manifest" | jq -r '.version')"
endpoint_count="$(echo "$manifest" | jq -r '.counts.total // 0')"

echo "== Platform Contract Audit =="
echo "domain=${DOMAIN}"
echo "contract_version=${contract_version}"
echo "endpoint_count=${endpoint_count}"

mapfile -t contract_paths < <(echo "$manifest" | jq -r '.endpoints[].path')
for path in "${contract_paths[@]}"; do
  code="$(fetch_code "$DOMAIN$path" || true)"
  if [[ "$code" == "200" ]]; then
    pass "endpoint $path returns 200"
  else
    fail "endpoint $path unexpected status $code"
  fi
done

canonical_headers="$(fetch_headers "$DOMAIN/api/platform/status" || true)"
if echo "$canonical_headers" | grep -qi '^X-Sapphire-API-Tier: canonical'; then
  pass "canonical endpoint exposes X-Sapphire-API-Tier"
else
  fail "canonical endpoint missing X-Sapphire-API-Tier header"
fi
if echo "$canonical_headers" | grep -qi '^X-Sapphire-Contract-Version:'; then
  pass "canonical endpoint exposes X-Sapphire-Contract-Version"
else
  fail "canonical endpoint missing X-Sapphire-Contract-Version header"
fi

for alias in /api/status /api/business-brief /api/logs /api/trades /api/contracts; do
  alias_headers="$(fetch_headers "$DOMAIN$alias" || true)"
  if echo "$alias_headers" | grep -qi '^Deprecation: true'; then
    pass "legacy alias $alias exposes Deprecation header"
  else
    fail "legacy alias $alias missing Deprecation header"
  fi
  if echo "$alias_headers" | grep -qi '^Link: .*successor-version'; then
    pass "legacy alias $alias exposes successor Link header"
  else
    fail "legacy alias $alias missing successor Link header"
  fi
done

if [[ "$FAILURES" -gt 0 ]]; then
  echo "\nContract audit FAILED with ${FAILURES} issue(s)."
  exit 1
fi

echo "\nContract audit PASSED."
