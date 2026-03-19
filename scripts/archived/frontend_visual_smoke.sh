#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-https://sapphirealpha.xyz}"
AUTH_USER="${AUTH_USER:-sapphire}"
AUTH_PASS="${AUTH_PASS:-alpha2024}"
AUTH="${AUTH_USER}:${AUTH_PASS}"

FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

need_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command available: $cmd"
  else
    fail "missing command: $cmd"
  fi
}

need_cmd curl
need_cmd rg

fetch_html() {
  local url="$1"
  local dest="$2"
  local code
  code="$(curl -sS -u "$AUTH" -o "$dest" -w '%{http_code}' "$url" || true)"
  if [[ "$code" == "200" ]]; then
    pass "GET $url -> 200"
  else
    fail "GET $url -> $code"
  fi
}

assert_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if rg -q "$pattern" "$file"; then
    pass "$label"
  else
    fail "$label"
  fi
}

assert_not_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if rg -q "$pattern" "$file"; then
    fail "$label"
  else
    pass "$label"
  fi
}

tmp_overview="$(mktemp)"
tmp_arch="$(mktemp)"

fetch_html "${DOMAIN}/" "$tmp_overview"
fetch_html "${DOMAIN}/architecture" "$tmp_arch"

echo "== Homepage contract markers =="
assert_contains "$tmp_overview" "Execution_Intelligence" "overview includes Execution_Intelligence panel"
assert_contains "$tmp_overview" "MARKET_DRIVERS" "overview includes MARKET_DRIVERS section"
assert_contains "$tmp_overview" "execution-intel-feed" "overview includes execution intelligence feed anchor"
assert_contains "$tmp_overview" "radar-canvas|Zeitgeist_Universe|System_Radar" "overview includes universe/radar canvas panel"
assert_contains "$tmp_overview" "chain-velocity-strip" "overview includes chain velocity strip"
assert_contains "$tmp_overview" "radar-quality-badge|universe-quality-badge" "overview includes universe quality badge"
assert_not_contains "$tmp_overview" "href=\"/control\"" "overview does not expose /control navigation"

echo "== Architecture contract markers =="
assert_contains "$tmp_arch" "Topology_View" "architecture includes topology panel"
assert_contains "$tmp_arch" "Operational Brief" "architecture includes operational brief panel"
assert_contains "$tmp_arch" "Security_Posture" "architecture includes security posture section"
assert_contains "$tmp_arch" "function publicLabel" "architecture script includes public label mapping"

echo "== Public naming hygiene =="
assert_not_contains "$tmp_arch" "Alpha Engine" "architecture does not expose Alpha Engine naming"
assert_not_contains "$tmp_arch" "PM Hub" "architecture does not expose PM Hub naming"
assert_not_contains "$tmp_arch" "Telegram Bot" "architecture does not expose Telegram Bot naming"

rm -f "$tmp_overview" "$tmp_arch"

if [[ "$FAILURES" -gt 0 ]]; then
  echo
  echo "frontend visual smoke FAILED with ${FAILURES} issue(s)."
  exit 1
fi

echo
echo "frontend visual smoke PASSED."
