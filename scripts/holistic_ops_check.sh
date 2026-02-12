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

if ! command -v gcloud >/dev/null 2>&1; then
  echo "FAIL: gcloud CLI missing"
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "FAIL: jq missing"
  exit 1
fi

alpha_json="$(gcloud run services describe "${ALPHA_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${ALPHA_REGION}" \
  --format=json)"

check_env_var() {
  local key="$1"
  local expected_pattern="${2:-}"
  local value
  value="$(echo "${alpha_json}" | jq -r --arg name "${key}" '.spec.template.spec.containers[0].env[]? | select(.name==$name) | .value // empty')"
  if [[ -z "${value}" ]]; then
    echo "FAIL: missing env var ${key}"
    exit 1
  fi
  if [[ -n "${expected_pattern}" ]] && ! [[ "${value}" =~ ${expected_pattern} ]]; then
    echo "FAIL: ${key} has unexpected value: ${value}"
    exit 1
  fi
  echo "PASS: ${key}=${value}"
}

check_env_var "SAPPHIRE_ALLOWED_REPOS" "Sapphire"
check_env_var "SAPPHIRE_ALLOWED_GCP_PROJECTS" "sapphire-479610"
check_env_var "SAPPHIRE_BLOCKED_SCOPE_TERMS" "sapphireai"

elapsed="$(( $(date +%s) - start_epoch ))"
echo
echo "Holistic ops check PASSED in ${elapsed}s."
