#!/usr/bin/env bash
# Sapphire OS — Google Cloud Shell bootstrap (read-only by default)
#
# Purpose: one command after clone/pull to orient an away-from-plant operator.
# Safe defaults: inventory + print fences. No trading, no Telegram, no DNS
# mutation, no traffic cutovers, no secret dumps.
#
# Usage (from Sapphire repo root, or any cwd):
#   bash scripts/ops/gcp_cloudshell_bootstrap.sh
#   bash scripts/ops/gcp_cloudshell_bootstrap.sh --deep
#   PROJECT=tho-ai-agent REGION=us-central1 bash scripts/ops/gcp_cloudshell_bootstrap.sh
#
# Exit codes: 0 = orientation complete (even if some probes fail);
#             2 = not inside a Sapphire checkout and clone helper declined.

set -euo pipefail

PROJECT="${PROJECT:-tho-ai-agent}"
WEBSITE_PROJECT="${WEBSITE_PROJECT:-sapphire-479610}"
REGION="${REGION:-us-central1}"
BQ_LOCATION="${BQ_LOCATION:-US}"
DATASET="${DATASET:-sapphire}"
BUCKET="${BUCKET:-sapphire-data-lake}"
DEEP=0
OUT_DIR="${OUT_DIR:-}"
NO_COLOR="${NO_COLOR:-}"

for arg in "$@"; do
  case "$arg" in
    --deep) DEEP=1 ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
  esac
done

if [[ -n "$NO_COLOR" ]]; then
  C0=""; C1=""; C2=""; C3=""; C4=""
else
  C0=$'\033[0m'; C1=$'\033[36m'; C2=$'\033[33m'; C3=$'\033[32m'; C4=$'\033[31m'
fi

log()  { printf "%s[cloudshell]%s %s\n" "$C1" "$C0" "$*"; }
warn() { printf "%s[cloudshell]%s %s\n" "$C2" "$C0" "$*"; }
ok()   { printf "%s[cloudshell]%s %s\n" "$C3" "$C0" "$*"; }
bad()  { printf "%s[cloudshell]%s %s\n" "$C4" "$C0" "$*"; }

# ---------------------------------------------------------------------------
# Resolve repo root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ ! -f "$REPO_ROOT/docs/gcp-data-engineering.md" ]] && [[ ! -f "$REPO_ROOT/CLAUDE.md" ]]; then
  bad "This script must live under a Sapphire checkout (scripts/ops/)."
  exit 2
fi

cd "$REPO_ROOT"
log "repo: $REPO_ROOT"
log "git:  $(git rev-parse --short HEAD 2>/dev/null || echo unknown) · $(git branch --show-current 2>/dev/null || echo detached)"

HANDOFF="$REPO_ROOT/docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md"
ALPHA="$REPO_ROOT/docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md"

# ---------------------------------------------------------------------------
# Fences (always print first)
# ---------------------------------------------------------------------------
cat <<'FENCES'

═══════════════════════════════════════════════════════════════════════════
  SAPPHIRE CLOUD SHELL FENCES (non-negotiable)
═══════════════════════════════════════════════════════════════════════════
  ✅  Inventory BQ / GCS / Cloud Run / Vertex / cost posture
  ✅  Idempotent infra bootstrap (schemas, bucket lifecycle)
  ✅  Code PRs: paper / research / docs / dens / dashboards
  ✅  Session notes → data/grok-web-exports/ for plant densify

  ❌  Live trading / order place-cancel-replace / money movement
  ❌  THO / Project-Go-Forward client funds or prod cutovers
  ❌  Hermes / Telegram sends
  ❌  Secret values printed or committed
  ❌  DNS edits on orphan tho-ai-agent zone for sapphirealpha.xyz
  ❌  Cloud Run 100% traffic shift without owner phrase
  ❌  Always-on Vertex endpoints / uncapped training jobs
  ❌  Re-buy dust sleeve (IBIT/HOOD/PLTR/NVDA) or lift dens
═══════════════════════════════════════════════════════════════════════════

FENCES

# ---------------------------------------------------------------------------
# Tool checks
# ---------------------------------------------------------------------------
need_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "found $1"
    return 0
  fi
  warn "missing $1"
  return 1
}

need_cmd gcloud || true
need_cmd bq || true
need_cmd gsutil || true
need_cmd git || true
need_cmd python3 || true
need_cmd gh || true

# ---------------------------------------------------------------------------
# gcloud identity
# ---------------------------------------------------------------------------
if command -v gcloud >/dev/null 2>&1; then
  ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
  CUR_PROJ="$(gcloud config get-value project 2>/dev/null || true)"
  log "gcloud account: ${ACCOUNT:-none}"
  log "gcloud project: ${CUR_PROJ:-none} (bootstrap target: $PROJECT)"

  if [[ -z "$ACCOUNT" || "$ACCOUNT" == "(unset)" ]]; then
    warn "Not logged in. Run: gcloud auth login"
  fi

  if [[ "$CUR_PROJ" != "$PROJECT" ]]; then
    warn "Active project is '$CUR_PROJ' — setting to $PROJECT for this shell session config"
    gcloud config set project "$PROJECT" >/dev/null 2>&1 || warn "could not set project"
  fi
  gcloud config set run/region "$REGION" >/dev/null 2>&1 || true
else
  bad "gcloud not installed — open Cloud Shell (not a bare VM without SDK)"
fi

# ---------------------------------------------------------------------------
# Read-only inventory probes
# ---------------------------------------------------------------------------
section() { printf "\n%s── %s ──%s\n" "$C1" "$1" "$C0"; }

section "Project describe ($PROJECT)"
if command -v gcloud >/dev/null 2>&1; then
  gcloud projects describe "$PROJECT" --format='table(projectId,projectNumber,lifecycleState)' 2>/dev/null \
    || warn "cannot describe $PROJECT (auth/permissions?)"
fi

section "BigQuery dataset $PROJECT:$DATASET"
if command -v bq >/dev/null 2>&1; then
  if bq --project_id="$PROJECT" ls -n 50 "$DATASET" 2>/dev/null; then
    ok "dataset listing ok"
  else
    warn "dataset list failed — bootstrap_bigquery.sh may be needed later"
  fi
  if [[ "$DEEP" -eq 1 ]]; then
    bq query --project_id="$PROJECT" --use_legacy_sql=false --format=pretty \
      "SELECT table_id, row_count, ROUND(size_bytes/1048576,2) AS mb,
              TIMESTAMP_MILLIS(last_modified_time) AS last_modified
       FROM \`${PROJECT}.${DATASET}.__TABLES__\`
       ORDER BY last_modified_time DESC
       LIMIT 30" 2>/dev/null || warn "freshness query failed"
  fi
else
  warn "bq not available"
fi

section "GCS gs://$BUCKET"
if command -v gsutil >/dev/null 2>&1; then
  gsutil ls -b "gs://$BUCKET" 2>/dev/null && ok "bucket exists" || warn "bucket missing or no access"
  if [[ "$DEEP" -eq 1 ]]; then
    gsutil ls "gs://$BUCKET/raw/" 2>/dev/null | head -n 30 || true
  fi
else
  warn "gsutil not available"
fi

section "Pub/Sub topics ($PROJECT)"
if command -v gcloud >/dev/null 2>&1; then
  gcloud pubsub topics list --project="$PROJECT" --format='value(name)' 2>/dev/null | head -n 40 \
    || warn "pubsub list failed"
fi

section "Cloud Run ($PROJECT @ $REGION)"
if command -v gcloud >/dev/null 2>&1; then
  gcloud run services list --project="$PROJECT" --region="$REGION" \
    --format='table(metadata.name,status.url,status.conditions[0].status)' 2>/dev/null \
    || warn "Cloud Run list failed for $PROJECT"
fi

section "Cloud Run website project ($WEBSITE_PROJECT @ $REGION) [read-only]"
if command -v gcloud >/dev/null 2>&1; then
  gcloud run services list --project="$WEBSITE_PROJECT" --region="$REGION" \
    --format='table(metadata.name,status.url,status.conditions[0].status)' 2>/dev/null \
    || warn "Cloud Run list failed for $WEBSITE_PROJECT (expected if no IAM)"
fi

section "Vertex idle check ($REGION)"
if command -v gcloud >/dev/null 2>&1; then
  for kind in custom-jobs endpoints models; do
    count="$(gcloud ai "${kind}" list --region="$REGION" --project="$PROJECT" --format='value(name)' 2>/dev/null | wc -l | tr -d ' ')"
    log "vertex ${kind}: ${count:-?}"
  done
fi

section "Repo readiness scripts (local, no mutation)"
if [[ -f "$REPO_ROOT/scripts/ops/gcp_ai_inventory.py" ]]; then
  if [[ "$DEEP" -eq 1 ]]; then
    python3 "$REPO_ROOT/scripts/ops/gcp_ai_inventory.py" \
      --project "$PROJECT" --region "$REGION" --format markdown 2>/dev/null \
      | head -n 80 || warn "gcp_ai_inventory failed (network/auth)"
  else
    python3 "$REPO_ROOT/scripts/ops/gcp_ai_inventory.py" --no-external --format markdown 2>/dev/null \
      | head -n 40 || warn "offline inventory helper failed"
    log "Re-run with --deep for live Vertex/BQ inventory via gcloud"
  fi
fi

if [[ "$DEEP" -eq 1 && -f "$REPO_ROOT/scripts/ops/cost_posture_report.py" ]]; then
  section "Cost posture (24h, read-only)"
  python3 "$REPO_ROOT/scripts/ops/cost_posture_report.py" --format markdown --hours 24 --log-limit 5 2>/dev/null \
    | head -n 100 || warn "cost posture failed"
fi

# ---------------------------------------------------------------------------
# Optional artifact
# ---------------------------------------------------------------------------
if [[ -n "$OUT_DIR" ]]; then
  mkdir -p "$OUT_DIR"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  note="$OUT_DIR/cloudshell-bootstrap-${stamp}.md"
  {
    echo "# Cloud Shell bootstrap artifact"
    echo "stamp: $stamp"
    echo "project: $PROJECT"
    echo "region: $REGION"
    echo "repo: $REPO_ROOT"
    echo "head: $(git rev-parse HEAD 2>/dev/null || true)"
  } > "$note"
  ok "wrote $note"
fi

# ---------------------------------------------------------------------------
# Next steps
# ---------------------------------------------------------------------------
section "Open these next"
if [[ -f "$HANDOFF" ]]; then
  ok "Handoff: $HANDOFF"
else
  warn "Handoff missing — pull latest main"
fi
if [[ -f "$ALPHA" ]]; then
  ok "Alpha NOW board: $ALPHA"
fi
cat <<EOF

Next commands:
  less docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md
  bash scripts/ops/gcp_cloudshell_bootstrap.sh --deep
  make google-readiness
  python3 scripts/ops/cost_posture_report.py --format markdown --hours 24

Idempotent data-plane bootstrap (only if inventory shows gaps):
  PROJECT=$PROJECT bash infra/gcp/bootstrap_gcs.sh
  PROJECT=$PROJECT bash infra/gcp/bootstrap_bigquery.sh

Session bridge (end of day):
  # write data/grok-web-exports/\$(date -u +%Y-%m-%d)_cloudshell-session.md
  # git add that path only → commit → push

EOF

ok "bootstrap complete — stay inside the fences"
exit 0
