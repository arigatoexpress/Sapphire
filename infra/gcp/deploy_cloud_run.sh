#!/usr/bin/env bash
# Deploy the Sapphire dashboard to Cloud Run (source-based deploy).
set -euo pipefail

PROJECT="${PROJECT:-sapphire-479610}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-sapphire-dashboard}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC_DIR="$REPO_ROOT/services/analytics_dashboard"
TAG="${TAG:-ci-$(git -C "$REPO_ROOT" rev-parse --short=7 HEAD)}"
ROUTE_TRAFFIC="${ROUTE_TRAFFIC:-0}"

log() { printf "\033[36m[run]\033[0m %s\n" "$*"; }

log "verifying Sapphire Analytics deploy source"
python3 "$REPO_ROOT/scripts/ops/verify_analytics_deploy_source.py" \
  --source-dir="$SRC_DIR"

log "deploying $SERVICE from $SRC_DIR"
deploy_args=(
  "$SERVICE"
  --source="$SRC_DIR"
  --region="$REGION"
  --project="$PROJECT"
  --platform=managed
  --memory=512Mi
  --cpu=1
  --min-instances=0
  --max-instances=5
  --update-env-vars="GCP_PROJECT=$PROJECT,BQ_DATASET=sapphire"
  --tag="$TAG"
  --quiet
)
if [ "$ROUTE_TRAFFIC" != "1" ]; then
  deploy_args+=(--no-traffic)
fi
gcloud run deploy "${deploy_args[@]}"

log "deployed:"
gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT" --format="value(status.url)"
