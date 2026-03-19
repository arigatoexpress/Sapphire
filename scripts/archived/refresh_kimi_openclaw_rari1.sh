#!/usr/bin/env bash
set -euo pipefail

# Safe refresh for rari1 Kimi/OpenClaw runtime:
# - preserve sensitive data + sessions
# - rebuild non-secret runtime/config surfaces
# - restart and verify service

KIMI_ROOT="${KIMI_ROOT:-/mnt/ssd/kimi-claw}"
OPENCLAW_ROOT="${OPENCLAW_ROOT:-/home/rari/.openclaw}"
SERVICE_NAME="${SERVICE_NAME:-openclaw-agent.service}"
BACKUP_ROOT="${BACKUP_ROOT:-${KIMI_ROOT}/backups}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${BACKUP_ROOT}/refresh-${TS}"
ARCHIVE="${RUN_DIR}/preserve-state-${TS}.tar.gz"

echo "[refresh] preparing ${RUN_DIR}"
mkdir -p "${RUN_DIR}"

required_paths=(
  "${KIMI_ROOT}"
  "${KIMI_ROOT}/config/.env"
  "${KIMI_ROOT}/venv/bin/python3"
  "${OPENCLAW_ROOT}"
)
for p in "${required_paths[@]}"; do
  if [[ ! -e "${p}" ]]; then
    echo "[refresh] missing required path: ${p}" >&2
    exit 1
  fi
done

echo "[refresh] stopping ${SERVICE_NAME}"
sudo systemctl stop "${SERVICE_NAME}" || true

echo "[refresh] backing up critical state"
tar -czf "${ARCHIVE}" \
  "${KIMI_ROOT}/config/.env" \
  "${KIMI_ROOT}/config/service-account.json" \
  "${KIMI_ROOT}/config/kimi-claw.yaml" \
  "${KIMI_ROOT}/config/kimi-main.md" \
  "${KIMI_ROOT}/data/agent.db" \
  "${KIMI_ROOT}/start_openclaw.py" \
  "${KIMI_ROOT}/src/bridge/telegram_bot.py" \
  "${KIMI_ROOT}/src/bridge/claude_llm.py" \
  "${OPENCLAW_ROOT}/openclaw.json" \
  "${OPENCLAW_ROOT}/credentials" \
  "${OPENCLAW_ROOT}/telegram" \
  "${OPENCLAW_ROOT}/workspace/.clawhub" \
  "${OPENCLAW_ROOT}/workspace-main" \
  "${OPENCLAW_ROOT}/workspace" \
  2>/dev/null || true

echo "[refresh] archive: ${ARCHIVE}"

echo "[refresh] refreshing bot runtime configuration"
export KIMI_ROOT OPENCLAW_ROOT
"${KIMI_ROOT}/venv/bin/python3" - <<'PY'
import json
import os
from pathlib import Path

kimi_root = Path(os.environ["KIMI_ROOT"])
openclaw_root = Path(os.environ["OPENCLAW_ROOT"])
env_path = kimi_root / "config" / ".env"
yaml_path = kimi_root / "config" / "kimi-claw.yaml"
oc_path = openclaw_root / "openclaw.json"

env_map = {}
for line in env_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env_map[k.strip()] = v.strip()

owner = env_map.get("TELEGRAM_OWNER_USER_ID", "").strip()
bot_token = env_map.get("TELEGRAM_BOT_TOKEN", "").strip()
if not owner or not bot_token:
    raise SystemExit("TELEGRAM_OWNER_USER_ID and TELEGRAM_BOT_TOKEN must be present in .env")

yaml_text = f"""# Kimi Claw runtime config (refreshed {Path('/').resolve()})
node:
  name: "rari1"
  role: "controller"
  primary_node: "127.0.0.1"
  primary_node_name: "rari1"
  heartbeat_interval: 10

network:
  bind_host: "0.0.0.0"
  api_port: 7474
  websocket_port: 7475
  use_encryption: false

llm:
  enabled: true
  max_tokens: 2048
  temperature: 0.4
  timeout: 120
  max_concurrent_calls: 1

analysis:
  enabled: true
  symbols: ["BTC-USD", "ETH-USD", "SOL-USD"]
  analysis_interval: 60

bridge:
  enabled: false
  sync_interval: 30
  data_sources: ["portfolio_state", "open_orders", "trading_history"]
  allowed_commands: ["status_report", "get_analysis", "assess_risk"]

storage:
  data_dir: "{kimi_root}/data"
  logs_dir: "{kimi_root}/logs"
  max_log_size_mb: 100
  max_log_files: 5

monitoring:
  enabled: true
  metrics_port: 9090
  health_check_interval: 30
  checks:
    cpu_threshold: 85
    memory_threshold: 90
    temp_threshold: 78
    disk_threshold: 92

telegram:
  enabled: true
  bot_token: null
  allowed_users: [{owner}]

security:
  api_key: ""
  allowed_ips: ["127.0.0.1", "100.64.0.0/10", "192.168.0.0/16"]
"""
yaml_path.write_text(yaml_text)

if oc_path.exists():
    raw = json.loads(oc_path.read_text())
    agents = raw.setdefault("agents", {})
    agent_list = agents.get("list")
    if not isinstance(agent_list, list):
        agent_list = []
    clean = []
    for entry in agent_list:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).lower()
        if name in {"emerald", "obsidian"}:
            continue
        clean.append(entry)
    if not any(str(e.get("name", "")).lower() == "sapphire" for e in clean):
        clean.insert(0, {"name": "Sapphire", "model": "gpt-5-codex", "active": True})
    agents["list"] = clean
    defaults = agents.setdefault("defaults", {})
    defaults["name"] = "Sapphire"
    raw["agents"] = agents
    oc_path.write_text(json.dumps(raw, indent=2))
PY

echo "[refresh] ensuring ALLOWED_USERS in .env"
owner_id="$(grep -E '^TELEGRAM_OWNER_USER_ID=' "${KIMI_ROOT}/config/.env" | tail -n1 | cut -d= -f2- | tr -d '[:space:]')"
if [[ -n "${owner_id}" ]]; then
  if grep -qE '^ALLOWED_USERS=' "${KIMI_ROOT}/config/.env"; then
    sed -i "s/^ALLOWED_USERS=.*/ALLOWED_USERS=${owner_id}/" "${KIMI_ROOT}/config/.env"
  else
    printf "\nALLOWED_USERS=%s\n" "${owner_id}" >> "${KIMI_ROOT}/config/.env"
  fi
fi

echo "[refresh] reinstalling python dependencies"
"${KIMI_ROOT}/venv/bin/pip" install --quiet --upgrade pip setuptools wheel
"${KIMI_ROOT}/venv/bin/pip" install --quiet -r "${KIMI_ROOT}/requirements.txt"

echo "[refresh] cleaning stale cache + rotating logs"
find "${KIMI_ROOT}" -type d -name "__pycache__" -prune -exec rm -rf {} +
mkdir -p "${KIMI_ROOT}/logs"
for f in "${KIMI_ROOT}/logs/openclaw.log" "${KIMI_ROOT}/logs/openclaw.err"; do
  [[ -f "${f}" ]] && sudo cp "${f}" "${RUN_DIR}/$(basename "${f}").pre_refresh" || true
  sudo touch "${f}"
  sudo truncate -s 0 "${f}"
  sudo chown rari:rari "${f}" || true
done

echo "[refresh] starting ${SERVICE_NAME}"
sudo systemctl start "${SERVICE_NAME}"
sleep 4

echo "[refresh] service status"
systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,22p'
echo "---"
tail -n 60 "${KIMI_ROOT}/logs/openclaw.err" || true

echo "[refresh] done"
echo "[refresh] rollback archive: ${ARCHIVE}"
