#!/bin/bash
# llama.cpp RPC server setup for Raspberry Pi (rari1 / rari2)
# Enables distributed inference: Windows GPU offloads layers to Pi RAM
#
# Architecture:
#   Windows GPU (llama-server --rpc 100.x.x.x:50052,100.x.x.y:50052)
#     └── rari1 (rpc-server :50052) — ARM64, ~4 GB RAM available
#     └── rari2 (rpc-server :50052) — ARM64, ~4 GB RAM available
#
# Benefit: 14B models (9.3 GB) that exceed 8 GB Mac RAM can partially
#   offload layers to Pi nodes via llama.cpp RPC, sharing computation.
#
# Prerequisites:
#   - SSH access to rari1 (rari1 SSH is currently refused — needs sshd restart)
#   - rari2 needs power cycle (currently offline)
#   - Pi must have build-essential, cmake, git installed
#   - Direct Ethernet link (10.0.0.1/10.0.0.2) or Tailscale (preferred for latency)
#
# BLOCKER: rari1 SSH is refused (22). Physical access required to start sshd:
#   sudo systemctl start ssh && sudo systemctl enable ssh
#
# Usage:
#   # From Mac, run against rari1 when SSH is available:
#   ssh rari@100.x.x.x "bash -s" < infra/pi/rpc-server-setup.sh

set -e

PI_USER="${PI_USER:-rari}"
RPC_PORT=50052
LLAMA_CPP_DIR="$HOME/llama.cpp"

echo "=== llama.cpp RPC Server Setup ==="
echo "Host: $(hostname)"
echo "Port: $RPC_PORT"
echo ""

# ── 1. Install dependencies ───────────────────────────────────────────────────
echo "[1/5] Installing build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates

# ── 2. Clone / update llama.cpp ───────────────────────────────────────────────
echo "[2/5] Cloning llama.cpp..."
if [ -d "$LLAMA_CPP_DIR" ]; then
    git -C "$LLAMA_CPP_DIR" pull --rebase --autostash
else
    git clone --depth=1 https://github.com/ggml-org/llama.cpp.git "$LLAMA_CPP_DIR"
fi

# ── 3. Build rpc-server (ARM64, no GPU) ───────────────────────────────────────
echo "[3/5] Building rpc-server (ARM64 CPU)..."
cd "$LLAMA_CPP_DIR"
cmake -B build -DGGML_RPC=ON -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_BUILD_SERVER=OFF 2>&1 | tail -5
cmake --build build --target rpc-server -j$(nproc) 2>&1 | tail -10

RPC_BIN="$LLAMA_CPP_DIR/build/bin/rpc-server"
if [ ! -f "$RPC_BIN" ]; then
    echo "ERROR: rpc-server binary not found at $RPC_BIN"
    exit 1
fi
echo "Built: $RPC_BIN"

# ── 4. Install systemd service ────────────────────────────────────────────────
echo "[4/5] Installing systemd service..."
sudo tee /etc/systemd/system/llama-rpc.service > /dev/null <<EOF
[Unit]
Description=llama.cpp RPC Server
After=network.target

[Service]
Type=simple
User=$PI_USER
ExecStart=$RPC_BIN --host 0.0.0.0 --port $RPC_PORT
Restart=on-failure
RestartSec=5s

# Memory limit — leave some headroom for OS
MemoryMax=3800M
MemoryHigh=3500M

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable llama-rpc
sudo systemctl restart llama-rpc

# ── 5. Verify ─────────────────────────────────────────────────────────────────
echo "[5/5] Verifying..."
sleep 2
if systemctl is-active --quiet llama-rpc; then
    echo "SUCCESS: llama-rpc running on port $RPC_PORT"
    echo ""
    echo "Now on Windows, start llama-server with:"
    echo "  llama-server -m <model.gguf> -ngl 99 \\"
    echo "    --rpc $(hostname -I | awk '{print $1}'):$RPC_PORT \\"
    echo "    --host 0.0.0.0 --port 11434"
else
    echo "FAILED: check 'sudo journalctl -u llama-rpc -n 20'"
    exit 1
fi
