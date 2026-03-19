#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIRS=(
  "$ROOT_DIR/services/unified-frontend/templates"
  "$ROOT_DIR/services/unified-frontend/static/js"
)

FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

check_forbidden_paths() {
  local pattern="$1"
  local label="$2"
  if rg -n "$pattern" "${TARGET_DIRS[@]}" --glob '!**/*.min.*' >/tmp/frontend_drift_hits.txt 2>/dev/null; then
    fail "$label"
    sed 's/^/  /' /tmp/frontend_drift_hits.txt
  else
    pass "$label"
  fi
}

check_absence() {
  local pattern="$1"
  local label="$2"
  if rg -n "$pattern" "${TARGET_DIRS[@]}" --glob '!**/*.min.*' >/tmp/frontend_drift_hits.txt 2>/dev/null; then
    fail "$label"
    sed 's/^/  /' /tmp/frontend_drift_hits.txt
  else
    pass "$label"
  fi
}

echo "== Frontend Endpoint Drift Guard =="
echo "scope: ${TARGET_DIRS[*]}"

check_forbidden_paths '/api/market/prices' "deprecated endpoint /api/market/prices is not referenced"
check_forbidden_paths '/api/platform/health' "deprecated endpoint /api/platform/health is not referenced"
check_absence "fetch\\('/api|fetch\\(\\\"/api" "direct frontend fetch('/api...') calls are blocked (use platform-api.js wrappers)"

if [[ "$FAILURES" -gt 0 ]]; then
  echo
  echo "frontend endpoint drift check FAILED with ${FAILURES} issue(s)."
  exit 1
fi

echo
echo "frontend endpoint drift check PASSED."
