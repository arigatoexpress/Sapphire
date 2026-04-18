#!/usr/bin/env bash
# Deploy the GCS → BQ auto-ETL Cloud Function (gen2, eventarc trigger).
set -euo pipefail

PROJECT="${PROJECT:-tho-ai-agent}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-sapphire-data-lake}"
FN_NAME="${FN_NAME:-sapphire-gcs-to-bq}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cloud_functions/gcs_to_bq"

log() { printf "\033[36m[fn]\033[0m %s\n" "$*"; }

# Ensure required APIs
log "enabling APIs (cloudfunctions, run, eventarc, cloudbuild)"
gcloud services enable \
  cloudfunctions.googleapis.com \
  run.googleapis.com \
  eventarc.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT" --quiet >/dev/null

# Grant GCS service agent eventarc publisher role (required for storage→eventarc)
GCS_SA=$(gsutil kms serviceaccount -p "$PROJECT")
log "granting eventarc publisher to GCS SA $GCS_SA"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$GCS_SA" \
  --role="roles/pubsub.publisher" \
  --condition=None --quiet >/dev/null || true

# Grant default compute SA run.invoker + eventarc.eventReceiver (default runtime SA)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
log "granting eventReceiver + bigquery.dataEditor + storage.objectViewer to $COMPUTE_SA"
for role in roles/eventarc.eventReceiver roles/bigquery.dataEditor roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="$role" \
    --condition=None --quiet >/dev/null
done

log "deploying $FN_NAME (region=$REGION)"
gcloud functions deploy "$FN_NAME" \
  --gen2 \
  --runtime=python312 \
  --region="$REGION" \
  --source="$SRC_DIR" \
  --entry-point=parse_and_load \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=$BUCKET" \
  --trigger-location="$REGION" \
  --memory=512MB \
  --timeout=540s \
  --max-instances=5 \
  --set-env-vars="GCP_PROJECT=$PROJECT,BQ_DATASET=sapphire" \
  --project="$PROJECT" \
  --quiet

log "deployed. URL:"
gcloud functions describe "$FN_NAME" --gen2 --region="$REGION" --project="$PROJECT" --format="value(serviceConfig.uri)"
