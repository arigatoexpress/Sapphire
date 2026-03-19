#!/usr/bin/env bash
set -euo pipefail

# Sync one canonical live-policy contract across:
#   1) Cloud gateway prefilter
#   2) rari2 bot-lighter runtime policy
#   3) rari2 overnight explorer emit policy
#
# Usage:
#   scripts/sync_live_policy_contract.sh [profile] [host]
#
# Profiles:
#   sol_5m_ev_guarded (default)
#   sol_15m_luxalgo
#   sol_5m_chartprime

PROFILE="${1:-sol_5m_ev_guarded}"
HOST="${2:-rari@100.87.225.89}"
PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
GATEWAY_SERVICE="${GATEWAY_SERVICE:-sapphire-gateway}"

LIGHTER_ENV_REMOTE="/home/rari/Sapphire/services/bot-lighter/.env"
EXPLORER_ENV_REMOTE="/home/rari/Sapphire/services/bot-lighter/overnight_explorer.env"

LIVE_SYMBOLS=""
LIVE_TIMEFRAMES=""
LIVE_STRATEGIES=""
MIN_CONFIDENCE=""
BOT_SYMBOL_ALLOWLIST=""
CAP_NEAR_CHURN_RATIO="${CAP_NEAR_CHURN_RATIO:-0.90}"
CAP_NEAR_MIN_NET_EV_PCT="${CAP_NEAR_MIN_NET_EV_PCT:-0.10}"
CAP_NEAR_MIN_EV_EDGE_PCT="${CAP_NEAR_MIN_EV_EDGE_PCT:-0.20}"
REJECT_TAX_WINDOW_HOURS="${REJECT_TAX_WINDOW_HOURS:-24}"
MIN_ABS_EDGE_PCT="${MIN_ABS_EDGE_PCT:-0.05}"
MIN_NET_EDGE_PCT="${MIN_NET_EDGE_PCT:-0.02}"
EST_FEE_BPS="${EST_FEE_BPS:-4.5}"
EST_SLIPPAGE_BPS="${EST_SLIPPAGE_BPS:-2.5}"

case "${PROFILE}" in
  sol_5m_ev_guarded)
    LIVE_SYMBOLS="SOLUSDT"
    LIVE_TIMEFRAMES="5m"
    LIVE_STRATEGIES="ev_guarded_momentum_v2"
    MIN_CONFIDENCE="0.72"
    BOT_SYMBOL_ALLOWLIST="SOL"
    ;;
  sol_5m_overnight)
    LIVE_SYMBOLS="SOLUSDT"
    LIVE_TIMEFRAMES="5m"
    LIVE_STRATEGIES="ev_guarded_momentum_v2"
    MIN_CONFIDENCE="0.72"
    BOT_SYMBOL_ALLOWLIST="SOL"
    ;;
  sol_15m_luxalgo)
    LIVE_SYMBOLS="SOLUSDT"
    LIVE_TIMEFRAMES="15m"
    LIVE_STRATEGIES="luxalgo_msb_ob,smart_money_breakout,algoalpha_smb"
    MIN_CONFIDENCE="0.70"
    BOT_SYMBOL_ALLOWLIST="SOL"
    ;;
  sol_5m_chartprime)
    LIVE_SYMBOLS="SOLUSDT"
    LIVE_TIMEFRAMES="5m"
    LIVE_STRATEGIES="chartprime_tbt,trendline_breakout_targets"
    MIN_CONFIDENCE="0.70"
    BOT_SYMBOL_ALLOWLIST="SOL"
    ;;
  *)
    echo "Unknown profile: ${PROFILE}" >&2
    exit 1
    ;;
esac
PRIMARY_STRATEGY="${LIVE_STRATEGIES%%,*}"

echo "[1/4] Updating gateway live-policy env vars (${GATEWAY_SERVICE})..."
gcloud run services update "${GATEWAY_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --update-env-vars "^@^SAPPHIRE_TV_LIVE_SYMBOLS=${LIVE_SYMBOLS}@SAPPHIRE_TV_LIVE_TIMEFRAMES=${LIVE_TIMEFRAMES}@SAPPHIRE_TV_LIVE_STRATEGIES=${LIVE_STRATEGIES}@SAPPHIRE_TV_EXECUTION_PREFILTER=true@SAPPHIRE_TV_EXECUTION_MIN_CONFIDENCE=${MIN_CONFIDENCE}"

echo "[2/4] Patching rari2 bot-lighter + explorer env files..."
ssh -o BatchMode=yes -o ConnectTimeout=10 \
  "${HOST}" \
  LIVE_SYMBOLS="${LIVE_SYMBOLS}" \
  LIVE_TIMEFRAMES="${LIVE_TIMEFRAMES}" \
  LIVE_STRATEGIES="${LIVE_STRATEGIES}" \
  MIN_CONFIDENCE="${MIN_CONFIDENCE}" \
  BOT_SYMBOL_ALLOWLIST="${BOT_SYMBOL_ALLOWLIST}" \
  CAP_NEAR_CHURN_RATIO="${CAP_NEAR_CHURN_RATIO}" \
  CAP_NEAR_MIN_NET_EV_PCT="${CAP_NEAR_MIN_NET_EV_PCT}" \
  CAP_NEAR_MIN_EV_EDGE_PCT="${CAP_NEAR_MIN_EV_EDGE_PCT}" \
  REJECT_TAX_WINDOW_HOURS="${REJECT_TAX_WINDOW_HOURS}" \
  MIN_ABS_EDGE_PCT="${MIN_ABS_EDGE_PCT}" \
  MIN_NET_EDGE_PCT="${MIN_NET_EDGE_PCT}" \
  EST_FEE_BPS="${EST_FEE_BPS}" \
  EST_SLIPPAGE_BPS="${EST_SLIPPAGE_BPS}" \
  PRIMARY_STRATEGY="${PRIMARY_STRATEGY}" \
  LIGHTER_ENV="${LIGHTER_ENV_REMOTE}" \
  EXPLORER_ENV="${EXPLORER_ENV_REMOTE}" \
  'bash -s' <<'EOSH'
set -euo pipefail
upsert_env() {
  local file="$1"
  local key="$2"
  local value="$3"
  touch "$file"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed -i "s#^${key}=.*#${key}=${value}#" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

upsert_env "$LIGHTER_ENV" "LIGHTER_ENTRY_SYMBOL_ALLOWLIST" "$BOT_SYMBOL_ALLOWLIST"
upsert_env "$LIGHTER_ENV" "LIGHTER_ALLOWED_TIMEFRAMES" "$LIVE_TIMEFRAMES"
upsert_env "$LIGHTER_ENV" "LIGHTER_ALLOWED_STRATEGIES" "$LIVE_STRATEGIES"
upsert_env "$LIGHTER_ENV" "LIGHTER_ENTRY_MIN_CONFIDENCE" "$MIN_CONFIDENCE"
upsert_env "$LIGHTER_ENV" "LIGHTER_STRATEGY_REQUIRE_METADATA" "true"
upsert_env "$LIGHTER_ENV" "LIGHTER_CAP_NEAR_CHURN_ENABLED" "true"
upsert_env "$LIGHTER_ENV" "LIGHTER_CAP_NEAR_CHURN_RATIO" "$CAP_NEAR_CHURN_RATIO"
upsert_env "$LIGHTER_ENV" "LIGHTER_CAP_NEAR_MIN_NET_EV_PCT" "$CAP_NEAR_MIN_NET_EV_PCT"
upsert_env "$LIGHTER_ENV" "LIGHTER_CAP_NEAR_MIN_EV_EDGE_PCT" "$CAP_NEAR_MIN_EV_EDGE_PCT"
upsert_env "$LIGHTER_ENV" "LIGHTER_REJECT_TAX_WINDOW_HOURS" "$REJECT_TAX_WINDOW_HOURS"

upsert_env "$EXPLORER_ENV" "LIVE_EXEC_SYMBOLS" "$LIVE_SYMBOLS"
upsert_env "$EXPLORER_ENV" "LIVE_EXEC_TIMEFRAMES" "$LIVE_TIMEFRAMES"
upsert_env "$EXPLORER_ENV" "LIVE_EXEC_STRATEGIES" "$LIVE_STRATEGIES"
upsert_env "$EXPLORER_ENV" "STRATEGY" "$PRIMARY_STRATEGY"
upsert_env "$EXPLORER_ENV" "SYMBOLS" "$LIVE_SYMBOLS"
upsert_env "$EXPLORER_ENV" "STRICT_LIVE_MODE" "true"
upsert_env "$EXPLORER_ENV" "MIN_CONFIDENCE" "$MIN_CONFIDENCE"
upsert_env "$EXPLORER_ENV" "MIN_ABS_EDGE_PCT" "$MIN_ABS_EDGE_PCT"
upsert_env "$EXPLORER_ENV" "MIN_NET_EDGE_PCT" "$MIN_NET_EDGE_PCT"
upsert_env "$EXPLORER_ENV" "EST_FEE_BPS" "$EST_FEE_BPS"
upsert_env "$EXPLORER_ENV" "EST_SLIPPAGE_BPS" "$EST_SLIPPAGE_BPS"
upsert_env "$EXPLORER_ENV" "PUBLISH_RESEARCH_SIGNALS" "false"
echo "patched $LIGHTER_ENV"
echo "patched $EXPLORER_ENV"
EOSH

echo "[3/4] Restarting rari2 services..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" \
  "sudo systemctl restart lighter-trading lighter-overnight-explorer && sleep 4 && systemctl is-active lighter-trading && systemctl is-active lighter-overnight-explorer"

echo "[4/4] Verifying synced policy..."
echo "Gateway env:"
gcloud run services describe "${GATEWAY_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(spec.template.spec.containers[0].env)' \
  | tr ';' '\n' | grep -E 'SAPPHIRE_TV_LIVE_|SAPPHIRE_TV_EXECUTION_'

echo ""
echo "rari2 lighter env:"
ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" \
  "grep -E '^(LIGHTER_ENTRY_SYMBOL_ALLOWLIST|LIGHTER_ALLOWED_TIMEFRAMES|LIGHTER_ALLOWED_STRATEGIES|LIGHTER_ENTRY_MIN_CONFIDENCE|LIGHTER_STRATEGY_REQUIRE_METADATA|LIGHTER_CAP_NEAR_CHURN_ENABLED|LIGHTER_CAP_NEAR_CHURN_RATIO|LIGHTER_CAP_NEAR_MIN_NET_EV_PCT|LIGHTER_CAP_NEAR_MIN_EV_EDGE_PCT|LIGHTER_REJECT_TAX_WINDOW_HOURS)=' '${LIGHTER_ENV_REMOTE}'"

echo ""
echo "rari2 explorer env:"
ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" \
  "grep -E '^(SYMBOLS|STRICT_LIVE_MODE|STRATEGY|LIVE_EXEC_SYMBOLS|LIVE_EXEC_TIMEFRAMES|LIVE_EXEC_STRATEGIES|MIN_CONFIDENCE|MIN_ABS_EDGE_PCT|MIN_NET_EDGE_PCT|EST_FEE_BPS|EST_SLIPPAGE_BPS|PUBLISH_RESEARCH_SIGNALS)=' '${EXPLORER_ENV_REMOTE}'"

echo ""
echo "✅ Live policy contract synced for profile: ${PROFILE}"
