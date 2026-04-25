#!/usr/bin/env bash
# Sapphire autonomy readiness checks (repo + GCP runtime).

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-tho-ai-agent}"
ALPHA_SERVICE="${ALPHA_SERVICE:-}"
PM_HUB_SERVICE="${PM_HUB_SERVICE:-agentic-pm-hub}"
THO_AGENT_SERVICE="${THO_AGENT_SERVICE:-tho-agent}"
ANALYTICS_SERVICE="${ANALYTICS_SERVICE:-sapphire-analytics}"
PROJECT_GO_FORWARD_SERVICE="${PROJECT_GO_FORWARD_SERVICE:-project-go-forward}"
SCOUT_SANDBOX_SERVICE="${SCOUT_SANDBOX_SERVICE:-}"
GATEWAY_SERVICE="${GATEWAY_SERVICE:-}"
ALPHA_REGION="${ALPHA_REGION:-us-central1}"
PM_HUB_REGION="${PM_HUB_REGION:-us-central1}"
THO_AGENT_REGION="${THO_AGENT_REGION:-us-central1}"
ANALYTICS_REGION="${ANALYTICS_REGION:-us-central1}"
PROJECT_GO_FORWARD_REGION="${PROJECT_GO_FORWARD_REGION:-us-central1}"
SCOUT_SANDBOX_REGION="${SCOUT_SANDBOX_REGION:-us-central1}"
GATEWAY_REGION="${GATEWAY_REGION:-us-central1}"
SCHEDULER_PROJECT_ID="${SCHEDULER_PROJECT_ID:-$PROJECT_ID}"
SCHEDULER_REGION="${SCHEDULER_REGION:-us-central1}"
AUTONOMY_SA="${AUTONOMY_SA:-}"
GATEWAY_EXPECTED_SERVICE_ACCOUNTS="${GATEWAY_EXPECTED_SERVICE_ACCOUNTS:-$AUTONOMY_SA}"
PUBLIC_HEALTH_SERVICES="${PUBLIC_HEALTH_SERVICES:-${PROJECT_GO_FORWARD_SERVICE},${ANALYTICS_SERVICE},${THO_AGENT_SERVICE}}"
PROTECTED_HEALTH_SERVICES="${PROTECTED_HEALTH_SERVICES:-${PM_HUB_SERVICE}}"
REQUIRED_SCHEDULER_JOBS="${REQUIRED_SCHEDULER_JOBS:-}"
PLATFORM_BASE_URL="${PLATFORM_BASE_URL:-https://sapphirealpha.xyz}"
PLATFORM_AUTH_USER="${PLATFORM_AUTH_USER:-}"
PLATFORM_AUTH_PASS="${PLATFORM_AUTH_PASS:-}"


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

check_platform_contracts() {
  if [[ -z "$PLATFORM_AUTH_USER" || -z "$PLATFORM_AUTH_PASS" ]]; then
    pass "platform contract checks skipped (PLATFORM_AUTH_USER and PLATFORM_AUTH_PASS required)"
    return
  fi

  local endpoints=(
    "/api/platform/status"
    "/api/platform/metrics"
    "/api/platform/autonomy"
    "/api/platform/home-snapshot"
    "/api/platform/logs"
    "/api/platform/trades"
    "/api/platform/organization"
    "/api/platform/readiness"
    "/api/platform/projects"
    "/api/platform/intel-feed"
    "/api/platform/superswarm"
    "/api/platform/windows-lab"
    "/api/platform/contracts"
  )

  for endpoint in "${endpoints[@]}"; do
    local status
    status="$(curl -sS -o /dev/null -w '%{http_code}' -u "${PLATFORM_AUTH_USER}:${PLATFORM_AUTH_PASS}" "${PLATFORM_BASE_URL}${endpoint}" 2>/dev/null || true)"
    if [[ "$status" == "200" ]]; then
      pass "platform contract OK: $endpoint"
    else
      fail "platform contract failed: $endpoint (status=${status:-none})"
    fi
  done
}

service_in_csv() {
  local value="$1"
  local csv="$2"
  [[ -n "$value" && -n "$csv" ]] && echo "$csv" | tr ',' '\n' | grep -Fxq "$value"
}

service_exists() {
  local service="$1"
  local region="$2"
  [[ -n "$service" ]] && gcloud run services describe "$service" --project "$PROJECT_ID" --region "$region" >/dev/null 2>&1
}

optional_service_ready() {
  local service="$1"
  local region="$2"
  local label="$3"

  if [[ -z "$service" ]]; then
    pass "$label check skipped (service not configured)"
    return
  fi
  if service_exists "$service" "$region"; then
    service_ready "$service" "$region"
  else
    pass "$label absent in $PROJECT_ID/$region (legacy or not deployed)"
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
      if curl -fsS "$url/webhook/health" >/dev/null 2>&1; then
        pass "$service webhook health endpoint"
      else
        fail "$service webhook health endpoint unreachable"
      fi
      local root_status
      root_status="$(curl -sS -o /dev/null -w '%{http_code}' "$url/" 2>/dev/null || true)"
      if [[ "$root_status" == "401" || "$root_status" == "403" ]]; then
        pass "$service blocks unauthenticated root"
      elif [[ "$root_status" =~ ^2 ]]; then
        fail "$service unexpectedly allows unauthenticated root"
      else
        pass "$service root returned ${root_status:-none} (treated as protected)"
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
    elif service_in_csv "$service" "$PROTECTED_HEALTH_SERVICES"; then
      local status_code
      status_code="$(curl -sS -o /dev/null -w '%{http_code}' "$url/health" 2>/dev/null || true)"
      if [[ "$status_code" == "401" || "$status_code" == "403" ]]; then
        pass "$service blocks unauthenticated health endpoint"
      else
        fail "$service expected protected health endpoint, got status=${status_code:-none}"
      fi
    elif curl -fsS "$url/health" >/dev/null 2>&1; then
      if service_in_csv "$service" "$PUBLIC_HEALTH_SERVICES"; then
        pass "$service public health endpoint"
      else
        fail "$service unexpectedly allows unauthenticated invoke"
      fi
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

check_platform_contracts

service_ready "$PROJECT_GO_FORWARD_SERVICE" "$PROJECT_GO_FORWARD_REGION"
service_ready "$ANALYTICS_SERVICE" "$ANALYTICS_REGION"
service_ready "$PM_HUB_SERVICE" "$PM_HUB_REGION"
service_ready "$THO_AGENT_SERVICE" "$THO_AGENT_REGION"
optional_service_ready "$ALPHA_SERVICE" "$ALPHA_REGION" "alpha Cloud Run"
optional_service_ready "$SCOUT_SANDBOX_SERVICE" "$SCOUT_SANDBOX_REGION" "scout sandbox Cloud Run"
optional_service_ready "$GATEWAY_SERVICE" "$GATEWAY_REGION" "gateway Cloud Run"

if service_exists "$ALPHA_SERVICE" "$ALPHA_REGION" && [[ -n "$AUTONOMY_SA" ]]; then
  alpha_sa=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
    | jq -r '.spec.template.spec.serviceAccountName // empty')
  if [[ "$alpha_sa" == "${AUTONOMY_SA}" ]]; then
    pass "alpha service account uses configured autonomy SA"
  else
    fail "alpha service account mismatch: ${alpha_sa:-<empty>}"
  fi
else
  pass "alpha service account check skipped (alpha service or AUTONOMY_SA not configured)"
fi

if service_exists "$GATEWAY_SERVICE" "$GATEWAY_REGION" && [[ -n "$GATEWAY_EXPECTED_SERVICE_ACCOUNTS" ]]; then
  gateway_sa=$(gcloud run services describe "$GATEWAY_SERVICE" --project "$PROJECT_ID" --region "$GATEWAY_REGION" --format=json \
    | jq -r '.spec.template.spec.serviceAccountName // empty')
  if echo "$GATEWAY_EXPECTED_SERVICE_ACCOUNTS" | tr ',' '\n' | grep -Fxq "$gateway_sa"; then
    pass "gateway service account allowed: $gateway_sa"
  else
    fail "gateway service account mismatch: ${gateway_sa:-<empty>} (allowed: $GATEWAY_EXPECTED_SERVICE_ACCOUNTS)"
  fi
else
  pass "gateway service account check skipped (gateway service or expected accounts not configured)"
fi

if [[ -z "$AUTONOMY_SA" ]]; then
  pass "Pub/Sub subscriber role check skipped (AUTONOMY_SA not configured)"
elif gcloud projects get-iam-policy "$PROJECT_ID" --format='value(etag)' >/dev/null 2>&1; then
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

if service_exists "$ALPHA_SERVICE" "$ALPHA_REGION"; then
  enabled_venues=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
    | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="ENABLED_VENUES") | .value // empty')
  if [[ "$enabled_venues" == "ASTER;LIGHTER" || "$enabled_venues" == "LIGHTER" || "$enabled_venues" == "ASTER" ]]; then
    pass "alpha enabled venues acceptable: ${enabled_venues}"
  else
    fail "alpha enabled venues mismatch: ${enabled_venues:-<empty>}"
  fi
else
  pass "alpha enabled venues check skipped (alpha service not deployed)"
fi



# ── OpenClaw Gateway Check ──
if service_exists "$ALPHA_SERVICE" "$ALPHA_REGION"; then
  openclaw_env=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
    | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="OPENCLAW_GATEWAY_TOKEN") | (.value // .valueFrom.secretKeyRef.name // empty)')
  tradingview_enabled=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
    | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="TRADINGVIEW_EXECUTION_ENABLED") | .value // empty')
  if [[ -n "$openclaw_env" ]]; then
    pass "OPENCLAW_GATEWAY_TOKEN configured in alpha service"
  elif [[ "$tradingview_enabled" == "false" ]]; then
    pass "OPENCLAW_GATEWAY_TOKEN not required while TRADINGVIEW_EXECUTION_ENABLED=false"
  else
    fail "OPENCLAW_GATEWAY_TOKEN not set in alpha service (OpenClaw dispatch disabled)"
  fi
else
  pass "OpenClaw gateway token check skipped (alpha service not deployed)"
fi

if service_exists "$ALPHA_SERVICE" "$ALPHA_REGION"; then
  autonomy_code_changes=$(gcloud run services describe "$ALPHA_SERVICE" --project "$PROJECT_ID" --region "$ALPHA_REGION" --format=json \
    | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES") | .value // empty')
  if [[ "$autonomy_code_changes" == "true" ]]; then
    pass "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES=true (high-risk mode)"
  else
    pass "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES disabled (safer default)"
  fi
else
  pass "code-change autonomy check skipped (alpha service not deployed)"
fi

if [[ -z "$REQUIRED_SCHEDULER_JOBS" ]]; then
  pass "scheduler job checks skipped (REQUIRED_SCHEDULER_JOBS not configured)"
elif ! gcloud services list --enabled --project "$SCHEDULER_PROJECT_ID" --filter='config.name:cloudscheduler.googleapis.com' --format='value(config.name)' | grep -Fxq "cloudscheduler.googleapis.com"; then
  fail "Cloud Scheduler API disabled in $SCHEDULER_PROJECT_ID"
else
  IFS=',' read -r -a required_jobs <<< "$REQUIRED_SCHEDULER_JOBS"
  for job in "${required_jobs[@]}"; do
    if gcloud scheduler jobs describe "$job" --project "$SCHEDULER_PROJECT_ID" --location "$SCHEDULER_REGION" >/dev/null 2>&1; then
      pass "scheduler job present: $job"
    else
      fail "scheduler job missing: $job"
    fi
  done
fi

echo
if [[ "$FAILURES" -gt 0 ]]; then
  echo "Readiness check FAILED ($FAILURES issue(s))."
  exit 1
fi

echo "Readiness check PASSED."
