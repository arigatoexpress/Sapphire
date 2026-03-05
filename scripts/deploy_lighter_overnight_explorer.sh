#!/usr/bin/env bash
set -euo pipefail

# Deploy and run the overnight multi-symbol signal explorer on rari2.
# Usage:
#   scripts/deploy_lighter_overnight_explorer.sh [host]

HOST="${1:-rari@100.87.225.89}"
REMOTE_ROOT="/home/rari/Sapphire"
REMOTE_SCRIPT="${REMOTE_ROOT}/scripts/overnight_multi_symbol_explorer.py"
REMOTE_ENV="${REMOTE_ROOT}/services/bot-lighter/overnight_explorer.env"
SERVICE_NAME="lighter-overnight-explorer"
PROJECT_ID="${PROJECT_ID:-sapphire-479610}"

WEBHOOK_SECRET="$(gcloud secrets versions access latest --secret=SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET --project="$PROJECT_ID")"
if [[ -z "${WEBHOOK_SECRET}" ]]; then
  echo "Failed to load SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET" >&2
  exit 1
fi

echo "Syncing explorer script to ${HOST}..."
rsync -az --delete "${PWD}/scripts/overnight_multi_symbol_explorer.py" "${HOST}:${REMOTE_SCRIPT}"

echo "Writing env file on ${HOST}..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" "cat > '${REMOTE_ENV}' <<'EOF'
GATEWAY_WEBHOOK_URL=https://sapphire-gateway-s77j6bxyra-uc.a.run.app/webhook/tradingview
WEBHOOK_SECRET=${WEBHOOK_SECRET}
SYMBOLS=BTCUSDT,SOLUSDT
TIMEFRAME=5m
SCAN_SECONDS=15
SYMBOL_COOLDOWN_SECONDS=120
HISTORY_LIMIT=180
EMA_FAST=3
EMA_SLOW=6
EDGE_THRESHOLD_PCT=0.020
MIN_CONFIDENCE=0.72
LOCKED_SYMBOL=BTCUSDT
SOURCE=overnight-explorer
STRATEGY=overnight_ema_crossover
EOF
chmod 600 '${REMOTE_ENV}'"

echo "Installing systemd service..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "${HOST}" "sudo tee /etc/systemd/system/${SERVICE_NAME}.service >/dev/null <<'EOF'
[Unit]
Description=Sapphire Overnight Multi-Symbol Lighter Explorer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rari
WorkingDirectory=/home/rari/Sapphire
EnvironmentFile=/home/rari/Sapphire/services/bot-lighter/overnight_explorer.env
ExecStart=/usr/bin/python3 /home/rari/Sapphire/scripts/overnight_multi_symbol_explorer.py
Restart=always
RestartSec=5
TimeoutStopSec=45
KillMode=control-group

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}
sleep 3
systemctl is-active ${SERVICE_NAME}
journalctl -u ${SERVICE_NAME} -n 40 --no-pager"

echo "Overnight explorer deployed and running on ${HOST}."
