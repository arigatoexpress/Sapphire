#!/usr/bin/env bash
# Single-command holistic operations check for the Sapphire focused runtime.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
ALPHA_SERVICE="${ALPHA_SERVICE:-sapphire-alpha}"
ALPHA_REGION="${ALPHA_REGION:-us-central1}"

start_epoch="$(date +%s)"

echo "== Sapphire Holistic Ops Check =="
echo "Project: ${PROJECT_ID}"
echo "Alpha service: ${ALPHA_SERVICE} (${ALPHA_REGION})"
echo

./scripts/verify_focused_stack.sh

echo
echo "== Additional Scope Enforcement Checks =="
echo "INFO: scope enforcement is covered by scripts/verify_focused_stack.sh (focus guard + autonomy readiness + GCP scope reconcile)."

elapsed="$(( $(date +%s) - start_epoch ))"
echo
echo "Holistic ops check PASSED in ${elapsed}s."
