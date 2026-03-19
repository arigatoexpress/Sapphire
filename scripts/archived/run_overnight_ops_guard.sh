#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
RUN_CANARY_TEST="${RUN_CANARY_TEST:-true}"
CANARY_WAIT_SECONDS="${CANARY_WAIT_SECONDS:-120}"

echo "== Sapphire Overnight Ops Guard =="
echo "project=${PROJECT_ID} region=${REGION}"

echo
echo "[1/3] Strict production runtime check"
PROJECT_ID="${PROJECT_ID}" \
REGION="${REGION}" \
BOTTLENECK_DIGEST_STRICT=true \
BOTTLENECK_DIGEST_MAX_AGE_SEC="${BOTTLENECK_DIGEST_MAX_AGE_SEC:-10800}" \
RUN_BOTTLENECK_DIGEST=false \
./scripts/run_production_check.sh

if [[ "${RUN_CANARY_TEST}" == "true" ]]; then
  echo
  echo "[2/3] Live canary execution verification"
  PROJECT_ID="${PROJECT_ID}" \
  REGION="${REGION}" \
  WAIT_SECONDS="${CANARY_WAIT_SECONDS}" \
  ./scripts/run_unified_lighter_prod_test.sh
else
  echo
  echo "[2/3] Live canary execution verification (skipped by RUN_CANARY_TEST=false)"
fi

echo
echo "[3/3] Final strict production runtime check"
PROJECT_ID="${PROJECT_ID}" \
REGION="${REGION}" \
BOTTLENECK_DIGEST_STRICT=true \
BOTTLENECK_DIGEST_MAX_AGE_SEC="${BOTTLENECK_DIGEST_MAX_AGE_SEC:-10800}" \
RUN_BOTTLENECK_DIGEST=false \
./scripts/run_production_check.sh

echo
echo "Overnight ops guard PASSED."
