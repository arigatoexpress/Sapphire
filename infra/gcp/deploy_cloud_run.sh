#!/usr/bin/env bash
# Deploy the Sapphire Analytics dashboard to Cloud Run (source-based deploy).
set -euo pipefail

PROJECT="${PROJECT:-tho-ai-agent}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-sapphire-analytics}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../services/analytics_dashboard"

log() { printf "\033[36m[run]\033[0m %s\n" "$*"; }

# Grant the default compute SA bigquery.dataViewer (read-only on dataset)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
log "granting bigquery.dataViewer + bigquery.jobUser to $COMPUTE_SA"
for role in roles/bigquery.dataViewer roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="$role" \
    --condition=None --quiet >/dev/null || true
done

log "deploying $SERVICE from $SRC_DIR"
gcloud run deploy "$SERVICE" \
  --source="$SRC_DIR" \
  --region="$REGION" \
  --project="$PROJECT" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5 \
  --set-env-vars="GCP_PROJECT=$PROJECT,BQ_DATASET=sapphire" \
  --quiet

log "deployed:"
gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT" --format="value(status.url)"
