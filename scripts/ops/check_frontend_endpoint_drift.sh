#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ROOT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
fi

ENDPOINT_SCAN_ROOTS=(
  "$ROOT_DIR/services/dashboard/templates"
  "$ROOT_DIR/services/dashboard/static/js"
)
DIRECT_FETCH_SCAN_ROOTS=(
  "$ROOT_DIR/services/dashboard/static/js"
)

FAILURES=0
HITS_FILE="$(mktemp "${TMPDIR:-/tmp}/frontend_drift_hits.XXXXXX")"
ERROR_FILE="$(mktemp "${TMPDIR:-/tmp}/frontend_drift_errors.XXXXXX")"
trap 'rm -f "$HITS_FILE" "$ERROR_FILE"' EXIT

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

require_scan_roots() {
  local missing=0
  local root
  for root in "$@"; do
    if [[ ! -d "$root" ]]; then
      fail "scan root exists: $root"
      missing=1
    fi
  done
  return "$missing"
}

check_absence() {
  local pattern="$1"
  local label="$2"
  shift 2

  : >"$HITS_FILE"
  : >"$ERROR_FILE"

  set +e
  rg -n "$pattern" "$@" --glob '!**/*.min.*' >"$HITS_FILE" 2>"$ERROR_FILE"
  local status=$?
  set -e

  if [[ "$status" -eq 0 ]]; then
    fail "$label"
    sed 's/^/  /' "$HITS_FILE"
  elif [[ "$status" -eq 1 ]]; then
    pass "$label"
  else
    fail "$label (scan error)"
    sed 's/^/  /' "$ERROR_FILE"
  fi
}

check_forbidden_paths() { check_absence "$@"; }

echo "== Frontend Endpoint Drift Guard =="
echo "endpoint scope: ${ENDPOINT_SCAN_ROOTS[*]}"
echo "direct-fetch scope: ${DIRECT_FETCH_SCAN_ROOTS[*]}"

require_scan_roots "${ENDPOINT_SCAN_ROOTS[@]}" || true

if [[ "$FAILURES" -gt 0 ]]; then
  echo
  echo "frontend endpoint drift check FAILED with ${FAILURES} issue(s)."
  exit 1
fi

check_forbidden_paths '/api/market/prices' "deprecated endpoint /api/market/prices is not referenced" "${ENDPOINT_SCAN_ROOTS[@]}"
check_forbidden_paths '/api/platform/health' "deprecated endpoint /api/platform/health is not referenced" "${ENDPOINT_SCAN_ROOTS[@]}"
# Legacy templates still make inline fetches; enforce wrapper discipline for shared JS.
check_absence "fetch\\('/api|fetch\\(\\\"/api" "shared dashboard JS does not bypass platform-api.js wrappers" "${DIRECT_FETCH_SCAN_ROOTS[@]}"

if [[ "$FAILURES" -gt 0 ]]; then
  echo
  echo "frontend endpoint drift check FAILED with ${FAILURES} issue(s)."
  exit 1
fi

echo
echo "frontend endpoint drift check PASSED."
