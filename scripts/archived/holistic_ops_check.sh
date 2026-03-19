#!/usr/bin/env bash
# Single-command holistic operations check for the Sapphire focused runtime.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
ALPHA_SERVICE="${ALPHA_SERVICE:-sapphire-alpha}"
ALPHA_REGION="${ALPHA_REGION:-us-central1}"
RUN_PRODUCTION_CHECK="${RUN_PRODUCTION_CHECK:-true}"
RUN_VERIFY_FOCUSED_STACK="${RUN_VERIFY_FOCUSED_STACK:-true}"
RUN_BOTTLENECK_DIGEST="${RUN_BOTTLENECK_DIGEST:-false}"
BOTTLENECK_DIGEST_DRY_RUN="${BOTTLENECK_DIGEST_DRY_RUN:-true}"
BOTTLENECK_DIGEST_STRICT="${BOTTLENECK_DIGEST_STRICT:-true}"
BOTTLENECK_DIGEST_MAX_AGE_SEC="${BOTTLENECK_DIGEST_MAX_AGE_SEC:-10800}"

start_epoch="$(date +%s)"

echo "== Sapphire Holistic Ops Check =="
echo "Project: ${PROJECT_ID}"
echo "Alpha service: ${ALPHA_SERVICE} (${ALPHA_REGION})"
echo

if [[ "${RUN_VERIFY_FOCUSED_STACK}" == "true" ]]; then
  ./scripts/verify_focused_stack.sh
else
  echo "INFO: skipping verify_focused_stack.sh (RUN_VERIFY_FOCUSED_STACK=false)"
fi

if [[ "${RUN_PRODUCTION_CHECK}" == "true" ]]; then
  echo
  echo "== Production Runtime Verification =="
  PROJECT_ID="${PROJECT_ID}" \
  BOTTLENECK_DIGEST_STRICT="${BOTTLENECK_DIGEST_STRICT}" \
  BOTTLENECK_DIGEST_MAX_AGE_SEC="${BOTTLENECK_DIGEST_MAX_AGE_SEC}" \
  RUN_BOTTLENECK_DIGEST="${RUN_BOTTLENECK_DIGEST}" \
  BOTTLENECK_DIGEST_DRY_RUN="${BOTTLENECK_DIGEST_DRY_RUN}" \
  ./scripts/run_production_check.sh
fi

echo
echo "== Additional Scope Enforcement Checks =="
echo "INFO: scope enforcement is covered by scripts/verify_focused_stack.sh (focus guard + autonomy readiness + GCP scope reconcile)."

elapsed="$(( $(date +%s) - start_epoch ))"
echo
echo "Holistic ops check PASSED in ${elapsed}s."
