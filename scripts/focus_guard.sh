#!/usr/bin/env bash
# Sapphire focus guard: fail on scope drift in docs/config and verify core runtime inventory.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

# These terms represent prohibited legacy scope for current focused operation.
FORBIDDEN_REGEX='(hyperliquid|symphony|drift|sapphire-v2)'
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

if rg -n -i --glob '!**/node_modules/**' --glob '!.git/**' "${FORBIDDEN_REGEX}" "${SCAN_PATHS[@]}" >/tmp/sapphire_focus_guard_hits.txt 2>/dev/null; then
  fail "forbidden legacy scope terms detected"
  cat /tmp/sapphire_focus_guard_hits.txt
else
  pass "no forbidden legacy scope terms in authoritative docs and skills"
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
  if [[ -f "${file}" ]]; then
    pass "required skill present: ${file}"
  else
    fail "missing required skill: ${file}"
  fi
done

if command -v gcloud >/dev/null 2>&1; then
  ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1 || true)"
  if [[ -n "${ACCOUNT}" ]]; then
    pass "gcloud authenticated: ${ACCOUNT}"

    PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
    mapfile -t CURRENT_SERVICES < <(gcloud run services list --project "${PROJECT_ID}" --platform managed --format='value(name)' 2>/dev/null | sort || true)
    REQUIRED_SERVICES=(
      "sapphire-alpha"
      "sapphire-aster"
      "sapphire-lighter"
      "sapphire-gateway"
    )

    for svc in "${REQUIRED_SERVICES[@]}"; do
      if printf '%s\n' "${CURRENT_SERVICES[@]}" | rg -qx "${svc}"; then
        pass "required Cloud Run service exists: ${svc}"
      else
        fail "missing required Cloud Run service: ${svc}"
      fi
    done
  else
    fail "gcloud installed but no active account"
  fi
else
  fail "gcloud CLI missing"
fi

echo
if [[ "${FAILURES}" -gt 0 ]]; then
  echo "Focus guard FAILED (${FAILURES} issue(s))."
  exit 1
fi

echo "Focus guard PASSED."
