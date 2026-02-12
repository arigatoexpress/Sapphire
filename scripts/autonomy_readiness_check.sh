#!/usr/bin/env bash
# Sapphire autonomy readiness checks (repo + GCP runtime).

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
ALPHA_SERVICE="${ALPHA_SERVICE:-sapphire-alpha}"
ASTER_SERVICE="${ASTER_SERVICE:-sapphire-aster}"
LIGHTER_SERVICE="${LIGHTER_SERVICE:-sapphire-lighter}"
GATEWAY_SERVICE="${GATEWAY_SERVICE:-sapphire-gateway}"
ALPHA_REGION="${ALPHA_REGION:-us-central1}"
ASTER_REGION="${ASTER_REGION:-us-central1}"
LIGHTER_REGION="${LIGHTER_REGION:-europe-west1}"
GATEWAY_REGION="${GATEWAY_REGION:-us-central1}"
SCHEDULER_REGION="${SCHEDULER_REGION:-us-central1}"

FAILURES=0

pass() {
  echo "PASS: $1"
}

fail() {
  echo "FAIL: $1"
  FAILURES=$((FAILURES + 1))
}

check_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command available: $cmd"
  else
    fail "missing command: $cmd"
  fi
}

service_ready() {
  local service="$1"
  local region="$2"
  local desc

  if ! desc=$(gcloud run services describe "$service" --project "$PROJECT_ID" --region "$region" --format=json 2>/dev/null); then
    fail "$service describe failed"
    return
  fi

  local ready
  ready=$(echo "$desc" | jq -r '.status.conditions[]? | select(.type=="Ready") | .status' | head -n1)
  local url
  url=$(echo "$desc" | jq -r '.status.url // empty')

  if [[ "$ready" == "True" ]]; then
    pass "$service ready in $region"
  else
    fail "$service not ready in $region"
  fi

  if [[ -n "$url" ]]; then
    if curl -fsS "$url/health" >/dev/null 2>&1; then
      pass "$service health endpoint"
    else
      fail "$service health endpoint unexpected response"
    fi
  else
    fail "$service missing URL"
  fi
}

echo "== Sapphire Autonomy Readiness =="
echo "Project: $PROJECT_ID"

auth_account=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1 || true)
if [[ -n "$auth_account" ]]; then
  pass "gcloud authenticated as $auth_account"
else
  fail "gcloud auth missing"
fi

check_cmd gcloud
check_cmd jq
check_cmd curl

service_ready "$ALPHA_SERVICE" "$ALPHA_REGION"
service_ready "$ASTER_SERVICE" "$ASTER_REGION"
service_ready "$LIGHTER_SERVICE" "$LIGHTER_REGION"
service_ready "$GATEWAY_SERVICE" "$GATEWAY_REGION"

enabled_venues=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
  | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="ENABLED_VENUES") | .value // empty')
if [[ "$enabled_venues" == "ASTER;LIGHTER" ]]; then
  pass "alpha enabled venues pinned to ASTER;LIGHTER"
else
  fail "alpha enabled venues mismatch: ${enabled_venues:-<empty>}"
fi

required_jobs=(
  "sapphire-alpha-health-6h"
  "sapphire-aster-health-6h"
  "sapphire-lighter-health-6h"
  "sapphire-alpha-heartbeat-30m"
  "sapphire-alpha-status-daily"
  "sapphire-alpha-strategy-gate-daily"
)

for job in "${required_jobs[@]}"; do
  if gcloud scheduler jobs describe "$job" --project "$PROJECT_ID" --location "$SCHEDULER_REGION" >/dev/null 2>&1; then
    pass "scheduler job present: $job"
  else
    fail "scheduler job missing: $job"
  fi
done

echo
if [[ "$FAILURES" -gt 0 ]]; then
  echo "Readiness check FAILED ($FAILURES issue(s))."
  exit 1
fi

echo "Readiness check PASSED."
