#!/usr/bin/env bash
# CI-safe focused gate for Sapphire PRs.
#
# This intentionally runs a strict subset of holistic checks that does not
# require live gcloud auth. Full cloud checks are handled separately.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

FAILURES=0
PYTHON_BIN="${PYTHON_BIN:-python3}"

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

pass() {
  echo "PASS: $1"
}

fail() {
  echo "FAIL: $1"
  FAILURES=$((FAILURES + 1))
}

check_file() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    pass "file present: ${path}"
  else
    fail "missing file: ${path}"
  fi
}

echo "== Sapphire CI Focused Gate =="

FORBIDDEN_REGEX='(sapphire-v2|legacy[-_ ]?venue|deprecated[-_ ]?venue)'
SCAN_PATHS=(
  "README.md"
  "OPERATIONS_RUNBOOK.md"
  "MASTERPLAN.md"
  "LEARNINGS.md"
  "skills"
  "docs/SAPPHIRE_AUTONOMY_MASTER_PLAN.md"
  "docs/SAPPHIRE_ORGANIZATION.md"
  "docs/TRADINGVIEW_QUANT_WORKBENCH.md"
)

if rg -n -i --glob '!**/node_modules/**' --glob '!.git/**' "${FORBIDDEN_REGEX}" "${SCAN_PATHS[@]}" >/tmp/sapphire_ci_focus_hits.txt 2>/dev/null; then
  fail "forbidden legacy scope terms detected"
  cat /tmp/sapphire_ci_focus_hits.txt
else
  pass "no forbidden legacy scope terms in authoritative docs/skills"
fi

REQUIRED_SKILLS=(
  "skills/security-audit/SKILL.md"
  "skills/ci-cd/SKILL.md"
  "skills/deploy/SKILL.md"
  "skills/self-improve/SKILL.md"
  "skills/code-review/SKILL.md"
  "skills/dep-update/SKILL.md"
  "skills/git-ops/SKILL.md"
)

for file in "${REQUIRED_SKILLS[@]}"; do
  check_file "${file}"
done

if "${PYTHON_BIN}" -m py_compile \
  services/alpha-engine/shared/telegram_bot.py \
  services/alpha-engine/shared/health.py \
  services/alpha-engine/src/collaboration/forum.py \
  services/alpha-engine/src/security/virustotal_scanner.py \
  services/alpha-engine/src/signals/alpha_scanner.py \
  services/alpha-engine/src/telegram_handlers.py \
  services/alpha-engine/src/main.py; then
  pass "alpha-engine syntax compile"
else
  fail "alpha-engine syntax compile"
fi

if PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_asyncio.plugin \
  tests/unit/test_alpha_engine_telegram_control.py \
  tests/unit/test_virustotal_skill_scanner.py; then
  pass "telegram control unit tests"
else
  fail "telegram control unit tests"
fi

if [[ -d "sapphire-web" ]]; then
  pushd sapphire-web >/dev/null
  # package-lock.json is intentionally not tracked in this repo.
  if npm install --no-audit --no-fund && npm run build; then
    pass "sapphire-web production build"
  else
    fail "sapphire-web production build"
  fi

  if [[ "${RUN_VISUAL_TESTS:-0}" == "1" ]]; then
    if npx playwright install chromium && npm run test:visual; then
      pass "sapphire-web visual regression"
    else
      fail "sapphire-web visual regression"
    fi
  else
    echo "INFO: visual regression skipped (set RUN_VISUAL_TESTS=1 to enforce)"
  fi
  popd >/dev/null
else
  fail "missing sapphire-web directory"
fi

echo
if [[ "${FAILURES}" -gt 0 ]]; then
  echo "Focused CI gate FAILED (${FAILURES} issue(s))."
  exit 1
fi

echo "Focused CI gate PASSED."
