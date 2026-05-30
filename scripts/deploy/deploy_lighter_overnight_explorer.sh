#!/usr/bin/env bash
set -euo pipefail

# Deploy and run the overnight multi-symbol signal explorer on rari2.
# Usage:
#   scripts/deploy_lighter_overnight_explorer.sh [host]
# Optional env:
#   SPARK_MODE=true               enable per-symbol lane config in explorer
#   SPARK_LANE_CONFIG=/path.json   local file path of lane JSON config (synced to remote)
#   PRICE_PROVIDERS=coingecko,coinbase,kraken,binance,coincap,cryptocompare
#   SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
#   TIMEFRAME=5m
#   SCAN_SECONDS=30
#   SYMBOL_COOLDOWN_SECONDS=120
#   HISTORY_LIMIT=180
#   EMA_FAST=3
#   EMA_SLOW=6
#   EDGE_THRESHOLD_PCT=0.020
#   MOMENTUM_EDGE_THRESHOLD_PCT=0.010
#   MIN_CONFIDENCE=0.70
#   LOCKED_SYMBOL=
#   SOURCE=overnight-explorer
#   STRATEGY=ev_guarded_momentum_v2
#   LIVE_EXEC_SYMBOLS=SOLUSDT
#   LIVE_EXEC_TIMEFRAMES=5m
#   LIVE_EXEC_STRATEGIES=ev_guarded_momentum_v2
#   MIN_ABS_EDGE_PCT=0.05
#   EST_FEE_BPS=4.5
#   EST_SLIPPAGE_BPS=2.5
#   MIN_NET_EDGE_PCT=0.02
#   STRICT_LIVE_MODE=true
#   PUBLISH_RESEARCH_SIGNALS=false
#   COINGECKO_USE_PRO=true         use pro.coingecko API host and optional pro key
#   COINGECKO_API_KEY=<key>        optional API key for coingecko pro
#   HTTP_TIMEOUT=12               timeout (seconds) for provider requests
#   PROVIDER_TIMEOUT=12           timeout (seconds) per provider call
#   PROVIDER_MAX_RETRIES=2        retries per provider before giving up
#   PROVIDER_CYCLE_SUMMARY_EVERY=1 cycle log cadence
#   TIMEOUT_STOP_SEC=120          service stop timeout seconds

HOST="${1:-rari@100.x.x.y}"
REMOTE_ROOT="/home/rari/Sapphire"
REMOTE_SCRIPT="${REMOTE_ROOT}/scripts/overnight_multi_symbol_explorer.py"
REMOTE_ENV="${REMOTE_ROOT}/services/bot-lighter/overnight_explorer.env"
SERVICE_NAME="lighter-overnight-explorer"
PROJECT_ID="${PROJECT_ID:-sapphire-479610}"

SPARK_MODE="${SPARK_MODE:-false}"
SPARK_LANE_CONFIG="${SPARK_LANE_CONFIG:-}"
PRICE_PROVIDERS="${PRICE_PROVIDERS:-coingecko,coinbase,kraken,binance,coincap,cryptocompare}"
COINGECKO_USE_PRO="${COINGECKO_USE_PRO:-}"
COINGECKO_API_KEY="${COINGECKO_API_KEY:-}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT}"
TIMEFRAME="${TIMEFRAME:-5m}"
SCAN_SECONDS="${SCAN_SECONDS:-30}"
SYMBOL_COOLDOWN_SECONDS="${SYMBOL_COOLDOWN_SECONDS:-120}"
HISTORY_LIMIT="${HISTORY_LIMIT:-180}"
EMA_FAST="${EMA_FAST:-3}"
EMA_SLOW="${EMA_SLOW:-6}"
EDGE_THRESHOLD_PCT="${EDGE_THRESHOLD_PCT:-0.020}"
MOMENTUM_EDGE_THRESHOLD_PCT="${MOMENTUM_EDGE_THRESHOLD_PCT:-0.010}"
MIN_CONFIDENCE="${MIN_CONFIDENCE:-0.70}"
LOCKED_SYMBOL="${LOCKED_SYMBOL:-}"
SOURCE="${SOURCE:-overnight-explorer}"
STRATEGY="${STRATEGY:-ev_guarded_momentum_v2}"
LIVE_EXEC_SYMBOLS="${LIVE_EXEC_SYMBOLS:-SOLUSDT}"
LIVE_EXEC_TIMEFRAMES="${LIVE_EXEC_TIMEFRAMES:-5m}"
LIVE_EXEC_STRATEGIES="${LIVE_EXEC_STRATEGIES:-ev_guarded_momentum_v2}"
MIN_ABS_EDGE_PCT="${MIN_ABS_EDGE_PCT:-0.05}"
EST_FEE_BPS="${EST_FEE_BPS:-4.5}"
EST_SLIPPAGE_BPS="${EST_SLIPPAGE_BPS:-2.5}"
MIN_NET_EDGE_PCT="${MIN_NET_EDGE_PCT:-0.02}"
STRICT_LIVE_MODE="${STRICT_LIVE_MODE:-true}"
PUBLISH_RESEARCH_SIGNALS="${PUBLISH_RESEARCH_SIGNALS:-false}"
HTTP_TIMEOUT="${HTTP_TIMEOUT:-12}"
PROVIDER_TIMEOUT="${PROVIDER_TIMEOUT:-$HTTP_TIMEOUT}"
PROVIDER_MAX_RETRIES="${PROVIDER_MAX_RETRIES:-2}"
PROVIDER_CYCLE_SUMMARY_EVERY="${PROVIDER_CYCLE_SUMMARY_EVERY:-1}"
TIMEOUT_STOP_SEC="${TIMEOUT_STOP_SEC:-120}"
REMOTE_SPARK_CONFIG="${REMOTE_ROOT}/configs/overnight_spark_lanes.json"

_is_true() {
  case "${1,,}" in
    true|1|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

if _is_true "${SPARK_MODE}"; then
  if [[ -z "${SPARK_LANE_CONFIG}" && -f "${PWD}/configs/overnight_spark_lanes.json" ]]; then
    SPARK_LANE_CONFIG="${PWD}/configs/overnight_spark_lanes.json"
  fi

  if [[ -n "${SPARK_LANE_CONFIG}" && -f "${SPARK_LANE_CONFIG}" ]]; then
    echo "Syncing Spark lane config file to ${HOST}..."
    ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" "mkdir -p '${REMOTE_ROOT}/configs'"
    rsync -az --delete "${SPARK_LANE_CONFIG}" "${HOST}:${REMOTE_SPARK_CONFIG}"
    SPARK_LANE_CONFIG="${REMOTE_SPARK_CONFIG}"
  else
    echo "WARN: SPARK_MODE=true but Spark lane config not found. Running in default lane mode."
    SPARK_LANE_CONFIG=""
  fi
else
  SPARK_MODE="false"
  SPARK_LANE_CONFIG=""
fi

WEBHOOK_SECRET="$(gcloud secrets versions access latest --secret=SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET --project="${PROJECT_ID}")"
if [[ -z "${WEBHOOK_SECRET}" ]]; then
  echo "Failed to load SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET" >&2
  exit 1
fi

echo "Syncing explorer script to ${HOST}..."
rsync -az --delete "${PWD}/scripts/overnight_multi_symbol_explorer.py" "${HOST}:${REMOTE_SCRIPT}"

echo "Writing env file on ${HOST}..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" "cat > '${REMOTE_ENV}' <<EOF
GATEWAY_WEBHOOK_URL=https://sapphire-gateway-s77j6bxyra-uc.a.run.app/webhook/tradingview
WEBHOOK_SECRET=${WEBHOOK_SECRET}
SYMBOLS=${SYMBOLS}
TIMEFRAME=${TIMEFRAME}
SCAN_SECONDS=${SCAN_SECONDS}
SYMBOL_COOLDOWN_SECONDS=${SYMBOL_COOLDOWN_SECONDS}
HISTORY_LIMIT=${HISTORY_LIMIT}
EMA_FAST=${EMA_FAST}
EMA_SLOW=${EMA_SLOW}
EDGE_THRESHOLD_PCT=${EDGE_THRESHOLD_PCT}
MOMENTUM_EDGE_THRESHOLD_PCT=${MOMENTUM_EDGE_THRESHOLD_PCT}
MIN_CONFIDENCE=${MIN_CONFIDENCE}
LOCKED_SYMBOL=${LOCKED_SYMBOL}
SOURCE=${SOURCE}
STRATEGY=${STRATEGY}
LIVE_EXEC_SYMBOLS=${LIVE_EXEC_SYMBOLS}
LIVE_EXEC_TIMEFRAMES=${LIVE_EXEC_TIMEFRAMES}
LIVE_EXEC_STRATEGIES=${LIVE_EXEC_STRATEGIES}
MIN_ABS_EDGE_PCT=${MIN_ABS_EDGE_PCT}
EST_FEE_BPS=${EST_FEE_BPS}
EST_SLIPPAGE_BPS=${EST_SLIPPAGE_BPS}
MIN_NET_EDGE_PCT=${MIN_NET_EDGE_PCT}
STRICT_LIVE_MODE=${STRICT_LIVE_MODE}
PUBLISH_RESEARCH_SIGNALS=${PUBLISH_RESEARCH_SIGNALS}
PRICE_PROVIDERS=${PRICE_PROVIDERS}
COINGECKO_USE_PRO=${COINGECKO_USE_PRO}
COINGECKO_API_KEY=${COINGECKO_API_KEY}
HTTP_TIMEOUT=${HTTP_TIMEOUT}
PROVIDER_TIMEOUT=${PROVIDER_TIMEOUT}
PROVIDER_MAX_RETRIES=${PROVIDER_MAX_RETRIES}
PROVIDER_CYCLE_SUMMARY_EVERY=${PROVIDER_CYCLE_SUMMARY_EVERY}
SPARK_MODE=${SPARK_MODE}
SPARK_LANE_CONFIG=${SPARK_LANE_CONFIG}
EOF
chmod 600 '${REMOTE_ENV}'"

echo "Installing service ${SERVICE_NAME} on ${HOST}..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" "sudo tee /etc/systemd/system/${SERVICE_NAME}.service >/dev/null <<EOF
[Unit]
Description=Sapphire Overnight Multi-Symbol Lighter Explorer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rari
WorkingDirectory=${REMOTE_ROOT}
EnvironmentFile=${REMOTE_ENV}
ExecStart=/usr/bin/python3 ${REMOTE_SCRIPT}
Restart=always
RestartSec=5
TimeoutStopSec=${TIMEOUT_STOP_SEC}
KillMode=control-group
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}
sleep 3
systemctl is-active ${SERVICE_NAME}
journalctl -u ${SERVICE_NAME} -n 60 --no-pager"

echo "Overnight explorer deployed and running on ${HOST}."
