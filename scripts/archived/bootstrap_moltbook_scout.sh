#!/usr/bin/env bash
# Bootstrap a real Moltbook scout agent, store token in Secret Manager, and wire sapphire-alpha.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-sapphire-alpha}"

MOLTBOOK_REGISTER_URL="${MOLTBOOK_REGISTER_URL:-https://www.moltbook.com/api/v1/agents/register}"
MOLTBOOK_POST_URL="${MOLTBOOK_POST_URL:-https://www.moltbook.com/api/v1/posts}"

AGENT_NAME="${AGENT_NAME:-SAPPHIRE_SCOUT}"
AGENT_DESCRIPTION="${AGENT_DESCRIPTION:-Least-privilege Sapphire scout for external collaboration and public idea discovery.}"

TOKEN_SECRET="${TOKEN_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN}"
REGISTER_SECRET="${REGISTER_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL}"
POST_SECRET="${POST_SECRET:-SAPPHIRE_SCOUT_EXTERNAL_POST_URL}"

FORCE_REGISTER="${FORCE_REGISTER:-false}"
RUN_SMOKE_TESTS="${RUN_SMOKE_TESTS:-true}"
RUN_REGISTER_SMOKE="${RUN_REGISTER_SMOKE:-false}"
REGISTER_RETRIES="${REGISTER_RETRIES:-4}"
REGISTER_BASE_BACKOFF_SECONDS="${REGISTER_BASE_BACKOFF_SECONDS:-2}"
ALLOW_FALLBACK_TO_EXISTING_TOKEN="${ALLOW_FALLBACK_TO_EXISTING_TOKEN:-true}"
ALLOW_URL_ONLY_ON_REGISTER_FAILURE="${ALLOW_URL_ONLY_ON_REGISTER_FAILURE:-true}"

usage() {
  cat <<USAGE
Usage:
  AGENT_NAME='SAPPHIRE_SCOUT' \
  AGENT_DESCRIPTION='Least-privilege scout for Sapphire.' \
  ./scripts/bootstrap_moltbook_scout.sh

Optional env vars:
  PROJECT_ID, REGION, SERVICE_NAME
  MOLTBOOK_REGISTER_URL, MOLTBOOK_POST_URL
  TOKEN_SECRET, REGISTER_SECRET, POST_SECRET
  FORCE_REGISTER=true|false
  RUN_SMOKE_TESTS=true|false
  RUN_REGISTER_SMOKE=true|false
  REGISTER_RETRIES=1..6
  REGISTER_BASE_BACKOFF_SECONDS=1..15
  ALLOW_FALLBACK_TO_EXISTING_TOKEN=true|false
  ALLOW_URL_ONLY_ON_REGISTER_FAILURE=true|false
USAGE
}

ensure_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command missing: $cmd"
    exit 1
  fi
}

upsert_secret_version() {
  local secret_name="$1"
  local secret_value="$2"
  if [[ -z "$secret_value" ]]; then
    echo "ERROR: cannot write empty value for secret ${secret_name}"
    exit 1
  fi

  if ! gcloud secrets describe "$secret_name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "Creating secret: ${secret_name}"
    gcloud secrets create "$secret_name" --project "$PROJECT_ID" --replication-policy=automatic >/dev/null
  fi

  printf '%s' "$secret_value" | gcloud secrets versions add "$secret_name" \
    --project "$PROJECT_ID" \
    --data-file=- >/dev/null
}

ensure_cmd curl
ensure_cmd jq
ensure_cmd gcloud

if [[ -z "$AGENT_NAME" ]]; then
  echo "ERROR: AGENT_NAME is required"
  usage
  exit 2
fi

echo "== Bootstrap Moltbook Scout =="
echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME} (${REGION})"
echo "Agent name: ${AGENT_NAME}"

auth_token=""
claim_url=""
verification_code=""
existing_token=""
last_register_error=""
last_register_response=""
register_conflict=0

if gcloud secrets describe "$TOKEN_SECRET" --project "$PROJECT_ID" >/dev/null 2>&1; then
  existing_token="$(gcloud secrets versions access latest --secret="$TOKEN_SECRET" --project "$PROJECT_ID" 2>/dev/null || true)"
fi

if [[ -n "$existing_token" ]] && [[ "$FORCE_REGISTER" != "true" ]]; then
  echo "Token secret ${TOKEN_SECRET} already exists; reusing existing token (set FORCE_REGISTER=true to create a new Moltbook agent)."
  auth_token="$existing_token"
else
  if [[ "$FORCE_REGISTER" == "true" ]] && [[ -n "$existing_token" ]]; then
    echo "FORCE_REGISTER=true set; attempting new registration (existing token secret is available as fallback)."
  else
    echo "Registering new Moltbook scout agent..."
  fi
  register_payload="$(jq -nc --arg n "$AGENT_NAME" --arg d "$AGENT_DESCRIPTION" '{name:$n,description:$d}')"
  retries="$REGISTER_RETRIES"
  if ! [[ "$retries" =~ ^[0-9]+$ ]] || [[ "$retries" -lt 1 ]]; then
    retries=4
  elif [[ "$retries" -gt 6 ]]; then
    retries=6
  fi
  base_backoff="$REGISTER_BASE_BACKOFF_SECONDS"
  if ! [[ "$base_backoff" =~ ^[0-9]+$ ]] || [[ "$base_backoff" -lt 1 ]]; then
    base_backoff=2
  elif [[ "$base_backoff" -gt 15 ]]; then
    base_backoff=15
  fi

  for attempt in $(seq 1 "$retries"); do
    bundle="$(curl -sSL --connect-timeout 10 --max-time 35 -X POST "$MOLTBOOK_REGISTER_URL" \
      -H 'Content-Type: application/json' \
      -d "$register_payload" \
      -w $'\n%{http_code}' || true)"
    http_status="$(printf '%s\n' "$bundle" | tail -n1 | tr -d '\r')"
    register_response="$(printf '%s\n' "$bundle" | sed '$d')"
    sanitized_response="$(printf '%s' "$register_response" | sed -E 's/moltbook_[A-Za-z0-9_-]+/[REDACTED_MOLTBOOK_KEY]/g')"
    api_success="$(echo "$register_response" | jq -r '.success // empty' 2>/dev/null || true)"
    api_error="$(echo "$register_response" | jq -r '.error // empty' 2>/dev/null || true)"

    auth_token="$(echo "$register_response" | jq -r '.agent.api_key // empty' 2>/dev/null || true)"
    claim_url="$(echo "$register_response" | jq -r '.agent.claim_url // empty' 2>/dev/null || true)"
    verification_code="$(echo "$register_response" | jq -r '.agent.verification_code // empty' 2>/dev/null || true)"

    if [[ "$http_status" =~ ^2[0-9][0-9]$ ]] && [[ -n "$auth_token" ]] && [[ "${api_success}" != "false" ]]; then
      echo "Moltbook agent registered on attempt ${attempt}/${retries}."
      break
    fi

    auth_token=""
    if [[ "${http_status:-}" == "409" ]]; then
      register_conflict=1
    fi
    last_register_error="attempt ${attempt}/${retries}: status=${http_status:-unknown} error=${api_error:-unknown}"
    last_register_response="$sanitized_response"
    echo "WARN: registration failed (${last_register_error})."
    if [[ "$attempt" -lt "$retries" ]]; then
      sleep_for=$((base_backoff * attempt))
      echo "Retrying in ${sleep_for}s..."
      sleep "$sleep_for"
    fi
  done

  if [[ -z "$auth_token" ]]; then
    if [[ "$ALLOW_FALLBACK_TO_EXISTING_TOKEN" == "true" ]] && [[ -n "$existing_token" ]]; then
      echo "Falling back to existing token from ${TOKEN_SECRET} because registration endpoint is unavailable."
      auth_token="$existing_token"
    elif [[ "$ALLOW_URL_ONLY_ON_REGISTER_FAILURE" == "true" ]]; then
      echo "WARN: Moltbook registration unavailable and no token fallback. Proceeding with URL-only bridge wiring."
      if [[ "$register_conflict" == "1" ]]; then
        echo "HINT: Moltbook reported the scout agent name already exists upstream. Recover the existing agent token or retry with a unique AGENT_NAME."
      fi
      auth_token=""
    else
      echo "ERROR: Moltbook registration failed and no fallback token is available."
      if [[ -n "$last_register_error" ]]; then
        echo "Last error: ${last_register_error}"
      fi
      if [[ -n "$last_register_response" ]]; then
        echo "Last response (sanitized):"
        echo "$last_register_response"
      fi
      exit 1
    fi
  fi
fi

if [[ -n "$auth_token" ]]; then
  upsert_secret_version "$TOKEN_SECRET" "$auth_token"
fi
upsert_secret_version "$REGISTER_SECRET" "$MOLTBOOK_REGISTER_URL"
upsert_secret_version "$POST_SECRET" "$MOLTBOOK_POST_URL"

if [[ -n "$auth_token" ]]; then
  echo "Secrets updated: ${TOKEN_SECRET}, ${REGISTER_SECRET}, ${POST_SECRET}"
else
  echo "Secrets updated (URL-only): ${REGISTER_SECRET}, ${POST_SECRET}"
fi

echo "Wiring Cloud Run secret bindings and validating bridge..."
MOLTBOOK_API_TOKEN="$auth_token" \
MOLTBOOK_REGISTER_URL="$MOLTBOOK_REGISTER_URL" \
MOLTBOOK_POST_URL="$MOLTBOOK_POST_URL" \
PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
SERVICE_NAME="$SERVICE_NAME" \
REGISTER_SECRET="$REGISTER_SECRET" \
POST_SECRET="$POST_SECRET" \
TOKEN_SECRET="$TOKEN_SECRET" \
RUN_SMOKE_TESTS="$RUN_SMOKE_TESTS" \
RUN_REGISTER_SMOKE="$RUN_REGISTER_SMOKE" \
ALLOW_URL_ONLY="true" \
"$(cd "$(dirname "$0")" && pwd)/wire_moltbook_bridge.sh"

if [[ -n "$claim_url" ]]; then
  echo
  echo "Claim URL (share with owner to verify): $claim_url"
fi
if [[ -n "$verification_code" ]]; then
  echo "Verification code: $verification_code"
fi

echo

echo "Bootstrap complete."
