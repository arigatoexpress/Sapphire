#!/usr/bin/env bash
# Pi Ollama Setup — Sapphire Tier 2 Inference Node
# Run as: ssh pi@<pi-ip> 'bash -s' < setup-ollama.sh
# Tested on: Raspberry Pi 4/5, Raspberry Pi OS (64-bit)
#
# After setup, Pi serves Ollama on :11434 (Tailscale-reachable)
# Models: nemotron-mini:4b (primary), gemma2:2b (backup), phi3:mini (ultra-light)

set -euo pipefail

OLLAMA_HOST="0.0.0.0"
MODELS=("nemotron-mini:4b" "gemma2:2b" "phi3:mini")

info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*"; }
error() { echo "[ERROR] $*" >&2; exit 1; }

# ── Verify ARM64 ─────────────────────────────────────────────────────────────
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  warn "Architecture is $ARCH — expected aarch64. Ollama supports ARM64."
fi

# ── Install Ollama ────────────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
  info "Ollama already installed: $(ollama --version)"
else
  info "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
  info "Ollama installed: $(ollama --version)"
fi

# ── Configure systemd to bind on 0.0.0.0 (for Tailscale access) ──────────────
OVERRIDE_DIR="/etc/systemd/system/ollama.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/env.conf"

if [[ ! -f "$OVERRIDE_FILE" ]]; then
  info "Configuring Ollama to bind on 0.0.0.0..."
  sudo mkdir -p "$OVERRIDE_DIR"
  sudo tee "$OVERRIDE_FILE" > /dev/null <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
EOF
  sudo systemctl daemon-reload
  info "Ollama systemd override written to $OVERRIDE_FILE"
else
  info "Ollama systemd override already present"
fi

# ── Start / restart Ollama ────────────────────────────────────────────────────
sudo systemctl enable ollama
sudo systemctl restart ollama
sleep 3

# Verify it's listening
if curl -s --max-time 5 "http://127.0.0.1:11434/api/tags" > /dev/null; then
  info "Ollama is up and responding"
else
  error "Ollama started but not responding on :11434 — check 'journalctl -u ollama'"
fi

# ── Pull models ───────────────────────────────────────────────────────────────
info "Pulling lightweight models (this will take a while on first run)..."
for model in "${MODELS[@]}"; do
  info "Pulling $model..."
  OLLAMA_HOST=127.0.0.1 ollama pull "$model" && info "  $model — OK" \
    || warn "  $model — FAILED (skipping, will retry next pull)"
done

# ── Verify models ─────────────────────────────────────────────────────────────
info "Installed models:"
OLLAMA_HOST=127.0.0.1 ollama list

# ── Quick smoke test ──────────────────────────────────────────────────────────
info "Smoke testing nemotron-mini:4b..."
RESULT=$(curl -sf --max-time 30 http://127.0.0.1:11434/api/chat \
  -d '{"model":"nemotron-mini:4b","messages":[{"role":"user","content":"Say OK"}],"stream":false}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['message']['content'][:50])" 2>/dev/null \
  || echo "FAILED")
info "Response: $RESULT"

# ── UFW firewall: allow Tailscale interface ───────────────────────────────────
if command -v ufw &>/dev/null; then
  TAILSCALE_IF=$(ip link show | grep -oP 'tailscale\d*' | head -1 || true)
  if [[ -n "$TAILSCALE_IF" ]]; then
    info "Allowing Ollama port 11434 on Tailscale interface ($TAILSCALE_IF)..."
    sudo ufw allow in on "$TAILSCALE_IF" to any port 11434 proto tcp \
      && info "  UFW rule added" \
      || warn "  UFW rule failed — check manually: sudo ufw allow 11434/tcp"
  else
    warn "Tailscale interface not found — ensure Tailscale is connected"
    info "Run manually: sudo ufw allow 11434/tcp (or scope to tailscale0)"
  fi
fi

# ── Print Tailscale IP ────────────────────────────────────────────────────────
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
info "───────────────────────────────────────────────"
info "Pi Ollama setup complete!"
info "Tailscale IP  : $TAILSCALE_IP"
info "Ollama port   : 11434"
info "Models ready  : ${MODELS[*]}"
info ""
info "Test from Mac:"
info "  curl http://$TAILSCALE_IP:11434/api/tags"
info ""
info "Update inference proxy if IP changed:"
info "  PI_RARI1 / PI_RARI2 in ~/Code/Sapphire/services/inference-proxy/app.py"
info "───────────────────────────────────────────────"
