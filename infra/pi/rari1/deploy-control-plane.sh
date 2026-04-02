#!/bin/bash
# Deploy control-plane to rari1
# Run from Mac: bash infra/pi/rari1/deploy-control-plane.sh
set -euo pipefail

RARI1="rari@100.120.191.1"
REMOTE_DIR="/mnt/ssd/sapphire/control-plane"
SERVICE="sapphire-control-plane"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

echo "── Syncing control-plane to rari1 ──────────────────────────────────"
rsync -az --delete \
    --exclude '.env' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'venv' \
    "${REPO_ROOT}/services/control-plane/" \
    "${RARI1}:${REMOTE_DIR}/"

echo "── Setting up venv + deps on rari1 ─────────────────────────────────"
ssh "${RARI1}" bash <<'REMOTE'
set -euo pipefail
cd /mnt/ssd/sapphire/control-plane

# Create dirs
mkdir -p /mnt/ssd/sapphire/logs
mkdir -p /mnt/ssd/sapphire/events

# Venv
if [ ! -d venv ]; then
    python3 -m venv venv
fi
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt

# Install (no google-cloud deps needed for local)
echo "Deps installed"
REMOTE

echo "── Installing systemd service ───────────────────────────────────────"
scp infra/pi/rari1/control-plane.service "${RARI1}:/tmp/sapphire-control-plane.service"
ssh "${RARI1}" bash <<'REMOTE'
sudo mv /tmp/sapphire-control-plane.service /etc/systemd/system/sapphire-control-plane.service
sudo systemctl daemon-reload
sudo systemctl enable sapphire-control-plane
sudo systemctl restart sapphire-control-plane
sleep 2
sudo systemctl status sapphire-control-plane --no-pager
REMOTE

echo ""
echo "✅ Control plane deployed to rari1:8082"
echo "   Check logs: ssh ${RARI1} journalctl -u sapphire-control-plane -f"
echo ""
echo "   Kimi bridge: POST http://100.120.191.1:8082/api/kimi/pm"
echo "                X-Control-Token: <CONTROL_PLANE_TOKEN>"
