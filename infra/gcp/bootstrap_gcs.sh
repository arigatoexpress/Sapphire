#!/usr/bin/env bash
# Bootstrap the Sapphire data lake bucket + folder placeholders + lifecycle.
set -euo pipefail

PROJECT="${PROJECT:-tho-ai-agent}"
BUCKET="${BUCKET:-sapphire-data-lake}"
LOCATION="${LOCATION:-us-central1}"
LIFECYCLE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bucket_lifecycle.json"

log() { printf "\033[36m[gcs]\033[0m %s\n" "$*"; }

if gsutil ls -b "gs://$BUCKET" >/dev/null 2>&1; then
  log "bucket gs://$BUCKET already exists"
else
  log "creating gs://$BUCKET in $LOCATION"
  gsutil mb -p "$PROJECT" -l "$LOCATION" -b on "gs://$BUCKET"
fi

# Versioning: keep old copies of JSONL snapshots
log "enabling versioning"
gsutil versioning set on "gs://$BUCKET" >/dev/null

# Uniform bucket-level access (best practice, simpler IAM)
log "setting uniform bucket-level access"
gsutil ubla set on "gs://$BUCKET" >/dev/null || true

# Lifecycle: age-tier raw/ to nearline→coldline→archive, delete old exports
log "applying lifecycle policy"
gsutil lifecycle set "$LIFECYCLE" "gs://$BUCKET"

# Folder placeholders (GCS has no real folders — use .keep placeholders)
log "seeding folder placeholders"
for prefix in raw/signals raw/predictions raw/chain raw/threats raw/metrics raw/leads raw/health \
              processed exports; do
  placeholder="gs://$BUCKET/${prefix}/.keep"
  if ! gsutil -q stat "$placeholder" 2>/dev/null; then
    printf "placeholder\n" | gsutil -q cp - "$placeholder" && echo "  + $prefix/"
  fi
done

log "done"
gsutil ls "gs://$BUCKET/"
