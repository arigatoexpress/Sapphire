#!/usr/bin/env bash
set -euo pipefail

CANONICAL_PATH="/Users/aribs/Sapphire"
CURRENT_PATH="$(pwd)"

if [[ "${CURRENT_PATH}" != "${CANONICAL_PATH}"* ]]; then
  echo "ERROR: Non-canonical workspace: ${CURRENT_PATH}"
  echo "Use ${CANONICAL_PATH} for production deploys."
  exit 1
fi

echo "OK: canonical workspace detected (${CURRENT_PATH})"

echo "Known non-canonical clones (for reference):"
for p in \
  "/Users/aribs/Documents/Organized/Codex Projects/github/Sapphire" \
  "/Users/aribs/sapphire-dashboard" \
  "/Users/aribs/sapphire-unified-frontend" \
  "/Users/aribs/sapphire-trading-infra"; do
  if [[ -d "$p" ]]; then
    echo "  - $p"
  fi
done
