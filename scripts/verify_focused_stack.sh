#!/usr/bin/env bash
# Canonical Sapphire focused-stack verification runner.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "== Sapphire Focused Stack Verification =="
./scripts/check_required_secrets.sh
./scripts/focus_guard.sh
./scripts/frontend_contract_check.sh
./scripts/autonomy_readiness_check.sh
./scripts/gcp_scope_reconcile.sh --strict

echo
echo "Focused stack verification PASSED."
