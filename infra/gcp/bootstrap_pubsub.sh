#!/usr/bin/env bash
# Bootstrap Pub/Sub topics + BigQuery subscriptions for real-time streaming.
#
# Pub/Sub "BigQuery subscriptions" auto-insert messages into BQ without a
# subscriber process. This requires the Pub/Sub service agent to have
# bigquery.dataEditor + bigquery.metadataViewer on the dataset.

set -euo pipefail

PROJECT="${PROJECT:-tho-ai-agent}"
DATASET="sapphire"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
PUBSUB_SA="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

log() { printf "\033[36m[pubsub]\033[0m %s\n" "$*"; }

# ---------------------------------------------------------------------------
# Grant Pub/Sub service agent BQ access on the dataset
# ---------------------------------------------------------------------------
log "granting BQ dataEditor + metadataViewer to $PUBSUB_SA"
for role in roles/bigquery.dataEditor roles/bigquery.metadataViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$PUBSUB_SA" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null
done

# ---------------------------------------------------------------------------
# Topics + BQ subscriptions: topic_name : table_name : schema_required
# use_topic_schema=false means we accept arbitrary JSON payloads and write
# them to a "data" BYTES column; if you want strict schema-writing, configure
# a Pub/Sub schema matching the BQ table. For the signals topic we route to
# the trading_signals table with use_topic_schema=false and write-metadata off,
# letting the publisher send the exact JSON row shape.
# ---------------------------------------------------------------------------
declare -a TOPICS=(
  "sapphire-signals:trading_signals"
  "sapphire-regime-changes:market_regime"
  "sapphire-alerts:"
  "sapphire-predictions:predictions"
  "sapphire-threats:threat_intel"
)

ensure_topic() {
  local t="$1"
  if gcloud pubsub topics describe "$t" --project="$PROJECT" >/dev/null 2>&1; then
    log "topic $t exists"
  else
    log "creating topic $t"
    gcloud pubsub topics create "$t" --project="$PROJECT" --quiet >/dev/null
  fi
}

ensure_bq_subscription() {
  local topic="$1" table="$2"
  local sub="${topic}-bq"
  local full_table="${PROJECT}:${DATASET}.${table}"

  if gcloud pubsub subscriptions describe "$sub" --project="$PROJECT" >/dev/null 2>&1; then
    log "subscription $sub exists"
    return
  fi

  log "creating BigQuery subscription $sub -> $full_table"
  # --use-table-schema: write JSON message fields directly to matching BQ columns
  # --drop-unknown-fields: ignore extra fields in messages that don't match the schema
  gcloud pubsub subscriptions create "$sub" \
    --topic="$topic" \
    --project="$PROJECT" \
    --bigquery-table="$full_table" \
    --use-table-schema \
    --drop-unknown-fields \
    --message-retention-duration=7d \
    --quiet >/dev/null
}

ensure_pull_subscription() {
  local topic="$1"
  local sub="${topic}-pull"
  if gcloud pubsub subscriptions describe "$sub" --project="$PROJECT" >/dev/null 2>&1; then
    log "subscription $sub exists"
    return
  fi
  log "creating pull subscription $sub"
  gcloud pubsub subscriptions create "$sub" \
    --topic="$topic" \
    --project="$PROJECT" \
    --ack-deadline=30 \
    --message-retention-duration=7d \
    --quiet >/dev/null
}

for spec in "${TOPICS[@]}"; do
  IFS=':' read -r topic table <<< "$spec"
  ensure_topic "$topic"
  if [[ -n "$table" ]]; then
    ensure_bq_subscription "$topic" "$table"
  else
    ensure_pull_subscription "$topic"
  fi
done

log "done"
gcloud pubsub topics list --project="$PROJECT" --format="value(name)"
echo "---"
gcloud pubsub subscriptions list --project="$PROJECT" --format="value(name)"
