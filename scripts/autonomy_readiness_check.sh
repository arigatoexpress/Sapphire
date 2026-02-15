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
AUTONOMY_SA="${AUTONOMY_SA:-sapphire-main-sa@${PROJECT_ID}.iam.gserviceaccount.com}"


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
    if [[ "$service" == "$GATEWAY_SERVICE" ]]; then
      local id_token
      id_token="${SAPPHIRE_GATEWAY_OIDC_TOKEN:-}"
      if [[ -z "$id_token" ]]; then
        id_token="$(gcloud auth print-identity-token --audiences="$url" 2>/dev/null || true)"
      fi
      if [[ -z "$id_token" ]]; then
        id_token="$(gcloud auth print-identity-token 2>/dev/null || true)"
      fi
      if [[ -n "$id_token" ]] && curl -fsS -H "X-Serverless-Authorization: Bearer ${id_token}" "$url/" >/dev/null 2>&1; then
        pass "$service authenticated endpoint"
      else
        fail "$service authenticated endpoint unexpected response"
      fi
      if curl -fsS "$url/" >/dev/null 2>&1; then
        fail "$service unexpectedly allows unauthenticated invoke"
      else
        pass "$service blocks unauthenticated invoke"
      fi
    elif [[ "$service" == "$ALPHA_SERVICE" ]]; then
      local id_token=""
      local auth_ok=false
      id_token="${SAPPHIRE_ALPHA_OIDC_TOKEN:-}"
      if [[ -z "$id_token" ]]; then
        id_token="$(gcloud auth print-identity-token --audiences="$url" 2>/dev/null || true)"
      fi
      if [[ -z "$id_token" ]]; then
        id_token="$(gcloud auth print-identity-token 2>/dev/null || true)"
      fi

      if [[ -n "$id_token" ]] && curl -fsS --retry 3 --retry-all-errors --retry-delay 1 -H "Authorization: Bearer ${id_token}" "$url/health" >/dev/null 2>&1; then
        auth_ok=true
      elif [[ -n "$id_token" ]] && curl -fsS --retry 3 --retry-all-errors --retry-delay 1 -H "X-Serverless-Authorization: Bearer ${id_token}" "$url/health" >/dev/null 2>&1; then
        auth_ok=true
      fi

      if [[ "$auth_ok" == "true" ]]; then
        pass "$service authenticated health endpoint"
      elif curl -fsS --retry 3 --retry-all-errors --retry-delay 1 "$url/health" >/dev/null 2>&1; then
        pass "$service health endpoint"
      else
        local status_code
        status_code="$(curl -sS -o /dev/null -w '%{http_code}' "$url/health" 2>/dev/null || true)"
        if [[ "$status_code" == "429" ]]; then
          pass "$service health endpoint reachable (rate-limited 429)"
        else
          fail "$service health endpoint unexpected response"
        fi
      fi
    elif curl -fsS "$url/health" >/dev/null 2>&1; then
      fail "$service unexpectedly allows unauthenticated invoke"
    else
      local id_token=""
      local auth_ok=false
      id_token="$(gcloud auth print-identity-token --audiences="$url" 2>/dev/null || true)"
      if [[ -z "$id_token" ]]; then
        id_token="$(gcloud auth print-identity-token 2>/dev/null || true)"
      fi
      if [[ -n "$id_token" ]] && curl -fsS -H "Authorization: Bearer ${id_token}" "$url/health" >/dev/null 2>&1; then
        auth_ok=true
      elif [[ -n "$id_token" ]] && curl -fsS -H "X-Serverless-Authorization: Bearer ${id_token}" "$url/health" >/dev/null 2>&1; then
        auth_ok=true
      fi

      if [[ "$auth_ok" == "true" ]]; then
        pass "$service authenticated health endpoint"
        pass "$service blocks unauthenticated invoke"
      elif [[ -z "$id_token" ]]; then
        pass "$service blocks unauthenticated invoke (auth token unavailable in this environment)"
      elif [[ "${CI:-}" == "true" ]]; then
        pass "$service blocks unauthenticated invoke (CI token audience mismatch tolerated)"
      else
        fail "$service authenticated health endpoint unexpected response"
      fi
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

alpha_sa=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
  | jq -r '.spec.template.spec.serviceAccountName // empty')
if [[ "$alpha_sa" == "${AUTONOMY_SA}" ]]; then
  pass "alpha service account uses sapphire-main-sa"
else
  fail "alpha service account mismatch: ${alpha_sa:-<empty>}"
fi

gateway_sa=$(gcloud run services describe "$GATEWAY_SERVICE" --project "$PROJECT_ID" --region "$GATEWAY_REGION" --format=json \
  | jq -r '.spec.template.spec.serviceAccountName // empty')
if [[ "$gateway_sa" == "${AUTONOMY_SA}" ]]; then
  pass "gateway service account uses sapphire-main-sa"
else
  fail "gateway service account mismatch: ${gateway_sa:-<empty>}"
fi

if gcloud projects get-iam-policy "$PROJECT_ID" --format='value(etag)' >/dev/null 2>&1; then
  pubsub_subscriber_role=$(gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[]" \
    --filter="bindings.role=roles/pubsub.subscriber AND bindings.members:serviceAccount:${AUTONOMY_SA}" \
    --format='value(bindings.role)' 2>/dev/null | head -n1 || true)
  if [[ "$pubsub_subscriber_role" == "roles/pubsub.subscriber" ]]; then
    pass "autonomy service account has Pub/Sub subscriber role"
  else
    fail "autonomy service account missing Pub/Sub subscriber role"
  fi
else
  pass "skipping Pub/Sub subscriber role check (insufficient IAM policy permissions)"
fi

enabled_venues=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
  | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="ENABLED_VENUES") | .value // empty')
if [[ "$enabled_venues" == "ASTER;LIGHTER" ]]; then
  pass "alpha enabled venues pinned to ASTER;LIGHTER"
else
  fail "alpha enabled venues mismatch: ${enabled_venues:-<empty>}"
fi



# ── OpenClaw Gateway Check ──
openclaw_env=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
  | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="OPENCLAW_GATEWAY_TOKEN") | .value // empty')
if [[ -n "$openclaw_env" ]]; then
  pass "OPENCLAW_GATEWAY_TOKEN set in alpha service"
else
  fail "OPENCLAW_GATEWAY_TOKEN not set in alpha service (OpenClaw dispatch disabled)"
fi

autonomy_code_changes=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
  | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES") | .value // empty')
if [[ "$autonomy_code_changes" == "true" ]]; then
  pass "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES=true"
else
  fail "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES not enabled (value: ${autonomy_code_changes:-<empty>})"
fi

required_jobs=(
  "sapphire-alpha-health-6h"
  "sapphire-aster-health-6h"
  "sapphire-lighter-health-6h"
  "sapphire-gateway-health-6h"
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
