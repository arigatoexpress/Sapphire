#!/usr/bin/env bash
# Register BigQuery scheduled queries via `bq mk --transfer_config`.
# Each scheduled query rebuilds a summary table the dashboard reads.
set -euo pipefail

PROJECT="${PROJECT:-tho-ai-agent}"
LOCATION="${LOCATION:-US}"

log() { printf "\033[36m[sq]\033[0m %s\n" "$*"; }

# Ensure the Data Transfer Service API is enabled
log "enabling bigquerydatatransfer API"
gcloud services enable bigquerydatatransfer.googleapis.com --project="$PROJECT" --quiet >/dev/null

# Grant BigQuery Transfer Service Agent the required role
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
DTS_SA="service-${PROJECT_NUMBER}@gcp-sa-bigquerydatatransfer.iam.gserviceaccount.com"
gcloud beta services identity create --service=bigquerydatatransfer.googleapis.com --project="$PROJECT" 2>&1 | tail -1
for role in roles/bigquerydatatransfer.serviceAgent roles/bigquery.dataEditor; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$DTS_SA" \
    --role="$role" \
    --condition=None --quiet >/dev/null || true
done

# name : schedule : body-file
declare -a QUERIES=(
  "daily_performance|every 24 hours|scheduled/daily_performance.sql"
  "weekly_regime|every mon 02:00|scheduled/weekly_regime.sql"
  "prediction_accuracy|every 24 hours|scheduled/prediction_accuracy.sql"
  "daily_threats|every 24 hours|scheduled/daily_threats.sql"
)

SQL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sql"

create_or_replace() {
  local name="$1" schedule="$2" body_rel="$3"
  local body_abs="$SQL_DIR/$body_rel"
  if [[ ! -f "$body_abs" ]]; then
    log "body missing: $body_abs (skipping $name)"
    return
  fi
  local query
  query=$(cat "$body_abs")

  # Delete any existing schedule with this display name (idempotent)
  local existing
  existing=$(bq ls --transfer_config --project_id="$PROJECT" --location="$LOCATION" --format=json 2>/dev/null \
    | /usr/local/bin/python3 -c "import json,sys;d=json.load(sys.stdin); print('\n'.join(c['name'] for c in d if c.get('displayName')=='$name'))" 2>/dev/null || true)
  if [[ -n "$existing" ]]; then
    log "removing existing schedule $name ($existing)"
    echo "y" | bq rm --transfer_config "$existing" >/dev/null 2>&1 || true
  fi

  log "creating scheduled query $name ($schedule)"
  bq mk --transfer_config \
    --project_id="$PROJECT" \
    --location="$LOCATION" \
    --display_name="$name" \
    --data_source=scheduled_query \
    --schedule="$schedule" \
    --target_dataset=sapphire \
    --service_account_name="sapphire-data-ops@${PROJECT}.iam.gserviceaccount.com" \
    --params="$(/usr/local/bin/python3 -c "import json; print(json.dumps({'query': open('$body_abs').read()}))")"
}

for spec in "${QUERIES[@]}"; do
  IFS='|' read -r name schedule body <<< "$spec"
  create_or_replace "$name" "$schedule" "$body"
done

log "done"
bq ls --transfer_config --project_id="$PROJECT" --location="$LOCATION"
