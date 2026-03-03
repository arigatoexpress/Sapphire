#!/usr/bin/env bash
# =============================================================================
# setup_kimi_rari1_ssd.sh
# Configure kimi-claw / OpenClaw on rari1 with SSD-backed storage
#
# rari1 = Controller Pi (Kimi/agent ops node)
# SSD:  /mnt/ssd (930GB Game Drive, already mounted, ext4)
#
# What this does:
#   1. Creates full directory structure on SSD
#   2. Syncs kimi-claw from rari2 → rari1 (config, src, scripts only — not venv)
#   3. Installs a fresh venv on rari1 SSD
#   4. Creates symlink: /home/rari/kimi-claw → /mnt/ssd/kimi-claw
#   5. Installs and enables the openclaw systemd service on rari1
#   6. Adds SSD to fstab if not already there
# =============================================================================
set -euo pipefail

RARI1="${RARI1:-rari@100.120.191.1}"
RARI2="${RARI2:-rari@100.87.225.89}"
SSD_ROOT="/mnt/ssd/kimi-claw"
KIMI_HOME="/home/rari/kimi-claw"
SERVICE_NAME="openclaw-agent"

echo "════════════════════════════════════════════════════"
echo "  OpenClaw SSD Setup — rari1 Controller Pi"
echo "  SSD: /mnt/ssd (930GB ext4)"
echo "════════════════════════════════════════════════════"
echo

# ── 1. Create SSD directory structure ────────────────────────────────────────
echo "[1/7] Creating SSD directory structure on rari1..."
ssh -o BatchMode=yes "$RARI1" "
  sudo mkdir -p ${SSD_ROOT}/{data,logs,models,output,workspace,config,venv,src,scripts}
  sudo chown -R rari:rari ${SSD_ROOT}
  chmod 750 ${SSD_ROOT}
  chmod 700 ${SSD_ROOT}/data   # SQLite db — private
  chmod 700 ${SSD_ROOT}/config # Configs may have tokens
  echo 'Directory structure created:'
  ls -la ${SSD_ROOT}/
"

# ── 2. Ensure SSD is in fstab for persistence ────────────────────────────────
echo
echo "[2/7] Checking fstab persistence..."
ssh -o BatchMode=yes "$RARI1" "
  if grep -q '/mnt/ssd' /etc/fstab; then
    echo 'SSD already in fstab — OK'
  else
    SDA2_UUID=\$(blkid -s UUID -o value /dev/sda2)
    echo \"Adding SSD to fstab: UUID=\${SDA2_UUID}\"
    echo \"UUID=\${SDA2_UUID}  /mnt/ssd  ext4  defaults,noatime  0  2\" | sudo tee -a /etc/fstab
    echo 'fstab updated'
  fi
"

# ── 3. Sync kimi-claw source from rari2 → rari1 (config + src, not venv) ────
echo
echo "[3/7] Syncing kimi-claw source from rari2 to rari1 SSD..."
# First pull from rari2 to mac, then push to rari1
ssh -o BatchMode=yes "$RARI2" "tar czf - \
  --exclude='kimi-claw/venv' \
  --exclude='kimi-claw/__pycache__' \
  --exclude='kimi-claw/*.pyc' \
  --exclude='kimi-claw/data/*.db-shm' \
  --exclude='kimi-claw/data/*.db-wal' \
  -C /home/rari kimi-claw/src kimi-claw/scripts kimi-claw/config \
  kimi-claw/start_openclaw.py kimi-claw/run_bot.sh kimi-claw/requirements.txt \
  kimi-claw/OPENCLAW_README.md kimi-claw/STRATEGY.md 2>/dev/null || true" | \
ssh -o BatchMode=yes "$RARI1" "cd ${SSD_ROOT} && tar xzf - --strip-components=1"
echo "Source sync complete"

# ── 4. Install Python venv on SSD ────────────────────────────────────────────
echo
echo "[4/7] Installing Python venv on SSD (rari1)..."
ssh -o BatchMode=yes "$RARI1" "
  if [[ ! -f '${SSD_ROOT}/venv/bin/python3' ]]; then
    python3 -m venv '${SSD_ROOT}/venv'
    '${SSD_ROOT}/venv/bin/pip' install --upgrade pip wheel
    if [[ -f '${SSD_ROOT}/requirements.txt' ]]; then
      '${SSD_ROOT}/venv/bin/pip' install --no-cache-dir -r '${SSD_ROOT}/requirements.txt'
    fi
    echo 'Venv installed at ${SSD_ROOT}/venv'
  else
    echo 'Venv already exists — skipping'
  fi
  '${SSD_ROOT}/venv/bin/python3' --version
  '${SSD_ROOT}/venv/bin/pip' install --upgrade certifi  # Always keep certifi current
"

# ── 5. Create symlink /home/rari/kimi-claw → /mnt/ssd/kimi-claw ─────────────
echo
echo "[5/7] Creating symlink: ${KIMI_HOME} → ${SSD_ROOT}..."
ssh -o BatchMode=yes "$RARI1" "
  if [[ -L '${KIMI_HOME}' ]]; then
    echo 'Symlink already exists: \$(readlink ${KIMI_HOME})'
  elif [[ -d '${KIMI_HOME}' ]]; then
    echo 'Backing up existing dir to ${KIMI_HOME}.bak'
    mv '${KIMI_HOME}' '${KIMI_HOME}.bak'
    ln -sf '${SSD_ROOT}' '${KIMI_HOME}'
    echo 'Symlink created'
  else
    ln -sf '${SSD_ROOT}' '${KIMI_HOME}'
    echo 'Symlink created'
  fi
  ls -la /home/rari/ | grep kimi-claw
"

# ── 6. Install systemd service for OpenClaw on rari1 ─────────────────────────
echo
echo "[6/7] Installing ${SERVICE_NAME} systemd service on rari1..."
ssh -o BatchMode=yes "$RARI1" "sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null" << 'SYSTEMD_UNIT'
[Unit]
Description=OpenClaw Autonomous Agent (Claude-powered) — rari1 Controller
Documentation=https://github.com/arigatoexpress/Sapphire
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rari
Group=rari
WorkingDirectory=/mnt/ssd/kimi-claw
Environment="PATH=/mnt/ssd/kimi-claw/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="KIMI_DATA_DIR=/mnt/ssd/kimi-claw/data"
Environment="KIMI_LOG_DIR=/mnt/ssd/kimi-claw/logs"
EnvironmentFile=/mnt/ssd/kimi-claw/config/.env
ExecStart=/mnt/ssd/kimi-claw/venv/bin/python3 /mnt/ssd/kimi-claw/start_openclaw.py
Restart=always
RestartSec=15
StandardOutput=append:/mnt/ssd/kimi-claw/logs/openclaw.log
StandardError=append:/mnt/ssd/kimi-claw/logs/openclaw.err
TimeoutStartSec=60
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SYSTEMD_UNIT

ssh -o BatchMode=yes "$RARI1" "
  sudo systemctl daemon-reload
  sudo systemctl enable ${SERVICE_NAME}
  echo 'Service installed and enabled (not yet started — configure .env first)'
  systemctl status ${SERVICE_NAME} --no-pager || true
"

# ── 7. Create .env template on SSD config ────────────────────────────────────
echo
echo "[7/7] Creating .env template in ${SSD_ROOT}/config/ on rari1..."
ssh -o BatchMode=yes "$RARI1" "
  if [[ ! -f '${SSD_ROOT}/config/.env' ]]; then
    cat > '${SSD_ROOT}/config/.env' << 'ENV_TEMPLATE'
# OpenClaw Agent — rari1 SSD Configuration
# FILL IN BEFORE STARTING: sudo nano /mnt/ssd/kimi-claw/config/.env

# LLM API (required — pick ONE)
ANTHROPIC_API_KEY=
# KIMI_API_KEY=  # alternative to Anthropic

# Telegram Bot (required for agent interface)
TELEGRAM_BOT_TOKEN=
# Set your Telegram user ID (get from @userinfobot):
TELEGRAM_OWNER_USER_ID=

# GCP
GCP_PROJECT_ID=sapphire-479610
GOOGLE_APPLICATION_CREDENTIALS=/mnt/ssd/kimi-claw/config/service-account.json

# Scout Sandbox (for outbound research dispatch)
SCOUT_SANDBOX_TOKEN=
SCOUT_SANDBOX_URL=https://sapphire-scout-sandbox-xxxxxxx-uc.a.run.app

# Agent data paths (pre-configured for SSD)
KIMI_DATA_DIR=/mnt/ssd/kimi-claw/data
KIMI_LOG_DIR=/mnt/ssd/kimi-claw/logs
KIMI_MODELS_DIR=/mnt/ssd/kimi-claw/models

# Trust level
OPENCLAW_TRUST_LEVEL=full
OPENCLAW_NODE_ID=rari1-apex
CLOUD_AGENT_DRY_RUN=false
ENV_TEMPLATE
    chmod 600 '${SSD_ROOT}/config/.env'
    echo '.env template created at ${SSD_ROOT}/config/.env'
  else
    echo '.env already exists — not overwriting'
  fi
"

echo
echo "════════════════════════════════════════════════════"
echo "  SSD Setup Complete!"
echo
echo "  NEXT STEPS:"
echo "  1. SSH rari1: nano /mnt/ssd/kimi-claw/config/.env"
echo "  2. Fill in: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_USER_ID"
echo "  3. Copy GCP service account: scp key.json rari@100.120.191.1:/mnt/ssd/kimi-claw/config/service-account.json"
echo "  4. Start agent: ssh $RARI1 'sudo systemctl start openclaw-agent'"
echo "  5. Check logs: ssh $RARI1 'tail -f /mnt/ssd/kimi-claw/logs/openclaw.log'"
echo "  6. IMPORTANT: Update Telegram allowed_users in kimi-claw config"
echo "════════════════════════════════════════════════════"
