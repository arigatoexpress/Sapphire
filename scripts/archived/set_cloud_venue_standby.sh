#!/usr/bin/env bash
set -euo pipefail

# Enforce standby posture for cloud venue services when edge execution is authoritative.
# Safe to re-run.

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"

run_update() {
  local service="$1"
  local region="$2"
  local env_vars="$3"

  echo "[standby] ${service} (${region})"
  gcloud run services update "${service}" \
    --project="${PROJECT_ID}" \
    --region="${region}" \
    --min-instances=0 \
    --update-env-vars="${env_vars}" \
    --update-labels="execution_plane=edge,runtime_role=standby,sapphire_scope=venue" \
    >/dev/null

  echo "  applied"
}

run_update "sapphire-lighter" "europe-west1" \
  "TRADING_ENABLED=false,ALLOW_LIVE_TRADING=0,SAPPHIRE_EXECUTION_AUTHORITY=standby_cloud"

run_update "sapphire-aster" "us-central1" \
  "TRADING_ENABLED=false,SAPPHIRE_EXECUTION_AUTHORITY=standby_cloud"

echo ""
echo "standby posture enforced for cloud venue services."
