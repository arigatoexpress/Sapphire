#!/usr/bin/env bash
# Sapphire Pi Agent Deployer
#
# Usage: ./deploy-agent.sh <agent-name> <target-pi>
#
# Examples:
#   ./deploy-agent.sh market-watchdog rari1
#   ./deploy-agent.sh health-monitor  rari2
#
# Agent names: market-watchdog, health-monitor
# Pi targets:  rari1 (100.x.x.x), rari2 (100.x.x.y)

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────────
SAPPHIRE_ROOT="${HOME}/Code/Sapphire"
AGENTS_DIR="${SAPPHIRE_ROOT}/agents"
DEPLOY_DIR="${SAPPHIRE_ROOT}/deploy/pi"
REMOTE_DIR="/home/rari/sapphire"
REMOTE_USER="rari"

declare -A PI_IPS=(
    ["rari1"]="100.x.x.x"
    ["rari2"]="100.x.x.y"
)

declare -A AGENT_FILES=(
    ["market-watchdog"]="market_watchdog.py"
    ["health-monitor"]="health_monitor.py"
)

declare -A AGENT_SERVICES=(
    ["market-watchdog"]="market-watchdog.service"
    ["health-monitor"]="health-monitor.service"
)

declare -A AGENT_CONFIGS=(
    ["market-watchdog"]="watchdog.yaml"
    ["health-monitor"]=""
)

declare -A AGENT_HEALTH_PORTS=(
    ["market-watchdog"]="19001"
    ["health-monitor"]="19002"
)

# ── Args ───────────────────────────────────────────────────────────────────────
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <agent-name> <target-pi>"
    echo ""
    echo "Agents:  ${!AGENT_FILES[*]}"
    echo "Targets: ${!PI_IPS[*]}"
    exit 1
fi

AGENT="$1"
TARGET="$2"

if [[ -z "${AGENT_FILES[$AGENT]+x}" ]]; then
    echo "❌ Unknown agent: $AGENT"
    echo "Known agents: ${!AGENT_FILES[*]}"
    exit 1
fi

if [[ -z "${PI_IPS[$TARGET]+x}" ]]; then
    echo "❌ Unknown target: $TARGET"
    echo "Known targets: ${!PI_IPS[*]}"
    exit 1
fi

PI_IP="${PI_IPS[$TARGET]}"
AGENT_PY="${AGENT_FILES[$AGENT]}"
SERVICE_FILE="${AGENT_SERVICES[$AGENT]}"
CONFIG_FILE="${AGENT_CONFIGS[$AGENT]}"
HEALTH_PORT="${AGENT_HEALTH_PORTS[$AGENT]}"

SSH="ssh ${REMOTE_USER}@${PI_IP}"
SCP="scp"

echo "🚀 Deploying ${AGENT} → ${TARGET} (${PI_IP})"
echo ""

# ── 1. Ping check ─────────────────────────────────────────────────────────────
echo "▸ Checking connectivity to ${PI_IP}..."
if ! ping -c 1 -W 3 "${PI_IP}" > /dev/null 2>&1; then
    echo "❌ Cannot reach ${PI_IP}. Check Tailscale: tailscale status"
    exit 1
fi
echo "  ✅ ${TARGET} reachable"

# ── 2. Prepare remote directory ───────────────────────────────────────────────
echo "▸ Creating remote directories..."
${SSH} "mkdir -p ${REMOTE_DIR}/agents ${REMOTE_DIR}/config ${REMOTE_DIR}/logs"
echo "  ✅ Directories ready"

# ── 3. Copy agent files ───────────────────────────────────────────────────────
echo "▸ Copying agent: ${AGENT_PY}..."
${SCP} "${AGENTS_DIR}/${AGENT_PY}" "${REMOTE_USER}@${PI_IP}:${REMOTE_DIR}/agents/${AGENT_PY}"
echo "  ✅ Agent code copied"

# Config file (optional)
if [[ -n "${CONFIG_FILE}" && -f "${SAPPHIRE_ROOT}/agents/config/${CONFIG_FILE}" ]]; then
    echo "▸ Copying config: ${CONFIG_FILE}..."
    ${SCP} "${SAPPHIRE_ROOT}/agents/config/${CONFIG_FILE}" \
           "${REMOTE_USER}@${PI_IP}:${REMOTE_DIR}/config/${CONFIG_FILE}"
    echo "  ✅ Config copied"
fi

# ── 4. Install dependencies ───────────────────────────────────────────────────
echo "▸ Checking Python dependencies..."
${SSH} "python3 -c 'import yaml' 2>/dev/null || pip3 install --quiet pyyaml || true"
echo "  ✅ Dependencies checked"

# ── 5. Install systemd service ────────────────────────────────────────────────
echo "▸ Installing systemd service: ${SERVICE_FILE}..."
${SCP} "${DEPLOY_DIR}/${SERVICE_FILE}" \
       "${REMOTE_USER}@${PI_IP}:/tmp/${SERVICE_FILE}"
${SSH} "sudo mv /tmp/${SERVICE_FILE} /etc/systemd/system/${SERVICE_FILE} && \
        sudo systemctl daemon-reload && \
        sudo systemctl enable ${AGENT}.service && \
        sudo systemctl restart ${AGENT}.service"
echo "  ✅ Service installed and started"

# ── 6. Verify ─────────────────────────────────────────────────────────────────
echo ""
echo "▸ Verifying deployment..."
sleep 3

# Check systemd status
SERVICE_STATUS=$(${SSH} "systemctl is-active ${AGENT}.service 2>/dev/null || echo 'unknown'")
if [[ "${SERVICE_STATUS}" == "active" ]]; then
    echo "  ✅ systemctl: ${AGENT}.service is active"
else
    echo "  ⚠️  systemctl: ${AGENT}.service status = ${SERVICE_STATUS}"
    echo "     Check: ssh ${REMOTE_USER}@${PI_IP} sudo journalctl -u ${AGENT} -n 20"
fi

# Health endpoint check
sleep 2
HTTP_STATUS=$(${SSH} "curl -s -o /dev/null -w '%{http_code}' http://localhost:${HEALTH_PORT}/health 2>/dev/null || echo '000'")
if [[ "${HTTP_STATUS}" == "200" ]]; then
    echo "  ✅ Health endpoint :${HEALTH_PORT}/health → HTTP 200"
else
    echo "  ⚠️  Health endpoint :${HEALTH_PORT}/health → HTTP ${HTTP_STATUS} (may still be starting)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment complete: ${AGENT} → ${TARGET}"
echo ""
echo "Commands:"
echo "  Logs:   ssh ${REMOTE_USER}@${PI_IP} sudo journalctl -u ${AGENT} -f"
echo "  Status: ssh ${REMOTE_USER}@${PI_IP} systemctl status ${AGENT}"
echo "  Health: curl http://${PI_IP}:${HEALTH_PORT}/health"
echo "  Stop:   ssh ${REMOTE_USER}@${PI_IP} sudo systemctl stop ${AGENT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
