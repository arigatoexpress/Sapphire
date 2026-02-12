#!/usr/bin/env bash
# Build and deploy sapphire-web to Firebase Hosting (sapphirealpha.xyz path).

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
TARGET_DOMAIN="${TARGET_DOMAIN:-sapphirealpha.xyz}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="${ROOT_DIR}/sapphire-web"
GIT_SHA="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_ID="${BUILD_ID:-web-${GIT_SHA}-firebase}"
BUILD_TIME_UTC="${BUILD_TIME_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

if ! command -v firebase >/dev/null 2>&1; then
  echo "firebase CLI is required but not installed."
  echo "Install: npm install -g firebase-tools"
  exit 1
fi

echo "== Sapphirebook Firebase Deploy =="
echo "Project: ${PROJECT_ID}"
echo "Domain: ${TARGET_DOMAIN}"
echo "Build ID: ${BUILD_ID}"
echo "Build time (UTC): ${BUILD_TIME_UTC}"

cd "${WEB_DIR}"
npm ci --no-audit --no-fund
VITE_BUILD_ID="${BUILD_ID}" VITE_BUILD_TIME_UTC="${BUILD_TIME_UTC}" npm run build

cd "${ROOT_DIR}"
firebase deploy --only hosting --project "${PROJECT_ID}"

echo
echo "Domain health check:"
curl -fsSI "https://${TARGET_DOMAIN}" | sed -n '1,20p'
echo
echo "Domain index asset fingerprint:"
curl -fsS "https://${TARGET_DOMAIN}" | sed -n 's/.*src="\/assets\/\([^"]*\)".*/\1/p'
