#!/usr/bin/env bash
# Bootstrap the Sapphire BigQuery data warehouse.
# Idempotent — safe to re-run. Uses bq mk with --schema files in ./schemas/.

set -euo pipefail

PROJECT="${PROJECT:-tho-ai-agent}"
DATASET="sapphire"
LOCATION="${LOCATION:-US}"
SCHEMA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/schemas"

log()  { printf "\033[36m[bq]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[bq]\033[0m %s\n" "$*"; }

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
if bq --project_id="$PROJECT" show --format=prettyjson "$DATASET" >/dev/null 2>&1; then
  log "dataset $PROJECT:$DATASET already exists — skipping create"
else
  log "creating dataset $PROJECT:$DATASET (location=$LOCATION)"
  bq --project_id="$PROJECT" --location="$LOCATION" mk \
    --dataset \
    --description="Sapphire OS data warehouse — trading signals, regime, predictions, threat intel, leads, inference metrics, service health" \
    --label=env:prod --label=owner:sapphire \
    "$PROJECT:$DATASET"
fi

# ---------------------------------------------------------------------------
# Tables — name : partition_field : cluster_fields
# ---------------------------------------------------------------------------
declare -a TABLES=(
  "trading_signals:timestamp:symbol,source,outcome"
  "predictions:timestamp:symbol,model"
  "market_regime:timestamp:regime"
  "inference_metrics:timestamp:tier,model"
  "threat_intel:timestamp:severity,source"
  "leads:timestamp:grade,status"
  "service_health:timestamp:service_name,status"
)

create_or_update() {
  local table="$1" part="$2" cluster="$3"
  local schema="$SCHEMA_DIR/${table}.json"
  local full="$PROJECT:$DATASET.$table"

  if [[ ! -f "$schema" ]]; then
    warn "schema missing: $schema — skipping $table"
    return
  fi

  if bq --project_id="$PROJECT" show --format=prettyjson "$full" >/dev/null 2>&1; then
    log "table $full exists — updating schema only"
    bq --project_id="$PROJECT" update "$full" "$schema" || warn "schema update failed for $table (incompatible change?)"
  else
    log "creating table $full (partition=$part, cluster=$cluster)"
    bq --project_id="$PROJECT" mk \
      --table \
      --time_partitioning_field="$part" \
      --time_partitioning_type=DAY \
      --clustering_fields="$cluster" \
      --description="Sapphire — $table" \
      --label=env:prod --label=owner:sapphire \
      "$full" "$schema"
  fi
}

for spec in "${TABLES[@]}"; do
  IFS=':' read -r name part cluster <<< "$spec"
  create_or_update "$name" "$part" "$cluster"
done

log "done — run 'bq ls $PROJECT:$DATASET' to verify"
