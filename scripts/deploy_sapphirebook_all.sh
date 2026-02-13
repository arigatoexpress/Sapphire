#!/usr/bin/env bash
# Deploy sapphire-web to Cloud Run and Firebase Hosting in one flow.
# This keeps sapphirealpha.xyz and Cloud Run aligned to the same build stamp.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-sapphirebook-web}"
TARGET_DOMAIN="${TARGET_DOMAIN:-sapphirealpha.xyz}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GIT_SHA="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_ID="${BUILD_ID:-web-$(date -u +%Y%m%d%H%M)-all-${GIT_SHA}}"
BUILD_TIME_UTC="${BUILD_TIME_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
SKIP_NPM_INSTALL="${SKIP_NPM_INSTALL:-0}"

pass() {
  echo "PASS: $1"
}

fail() {
  echo "FAIL: $1"
  exit 1
}

echo "== Sapphirebook Full Frontend Deploy =="
echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME}"
echo "Domain: ${TARGET_DOMAIN}"
echo "Build ID: ${BUILD_ID}"
echo "Build time (UTC): ${BUILD_TIME_UTC}"
echo

BUILD_ID="${BUILD_ID}" \
BUILD_TIME_UTC="${BUILD_TIME_UTC}" \
SKIP_NPM_INSTALL="${SKIP_NPM_INSTALL}" \
"${ROOT_DIR}/scripts/deploy_sapphirebook_web.sh"

BUILD_ID="${BUILD_ID}" \
BUILD_TIME_UTC="${BUILD_TIME_UTC}" \
SKIP_NPM_INSTALL=1 \
SKIP_BUILD=1 \
"${ROOT_DIR}/scripts/deploy_sapphirebook_firebase.sh"

CR_URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
[[ -n "${CR_URL}" ]] || fail "could not resolve Cloud Run URL for ${SERVICE_NAME}"
pass "resolved Cloud Run URL: ${CR_URL}"

CR_JS="$(curl -fsS "${CR_URL}" | rg -o 'index-[A-Za-z0-9_-]+\.js' -m1 || true)"
DOM_JS="$(curl -fsS "https://${TARGET_DOMAIN}" | rg -o 'index-[A-Za-z0-9_-]+\.js' -m1 || true)"
[[ -n "${CR_JS}" ]] || fail "could not resolve Cloud Run frontend bundle fingerprint"
[[ -n "${DOM_JS}" ]] || fail "could not resolve domain frontend bundle fingerprint"

echo "Cloud Run bundle: ${CR_JS}"
echo "Domain bundle: ${DOM_JS}"

if [[ "${CR_JS}" == "${DOM_JS}" ]]; then
  pass "bundle fingerprints match across Cloud Run and domain"
else
  echo "WARN: bundle fingerprints differ. Verifying build stamp + UI markers instead."
fi

curl -fsS "${CR_URL}/health" >/dev/null && pass "Cloud Run /health"
curl -fsSI "https://${TARGET_DOMAIN}" >/dev/null && pass "domain index reachable"

CR_BUNDLE="$(curl -fsS "${CR_URL}/assets/${CR_JS}")"
DOM_BUNDLE="$(curl -fsS "https://${TARGET_DOMAIN}/assets/${DOM_JS}")"

for marker in \
  "SAPPHIREBOOK FORUM" \
  "Architecture Pulse" \
  "Real-Time Event Stream" \
  "${BUILD_ID}"
do
  printf '%s' "${CR_BUNDLE}" | rg -q --fixed-strings "${marker}" \
    && pass "Cloud Run bundle contains marker: ${marker}" \
    || fail "Cloud Run bundle missing marker: ${marker}"

  printf '%s' "${DOM_BUNDLE}" | rg -q --fixed-strings "${marker}" \
    && pass "Domain bundle contains marker: ${marker}" \
    || fail "Domain bundle missing marker: ${marker}"
done

echo
echo "Frontend full deploy succeeded with synchronized build stamp: ${BUILD_ID}"
