#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-rari@100.120.191.1}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/rari/research-node}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="$LOCAL_ROOT/services/research-node/systemd"
RUNNER="$LOCAL_ROOT/services/research-node/research_batch_runner.py"

echo "== Deploy RARI1 Research Node =="
echo "host=$HOST"
echo "remote_root=$REMOTE_ROOT"

if [[ ! -f "$RUNNER" ]]; then
  echo "missing runner: $RUNNER" >&2
  exit 1
fi

for unit in \
  sapphire-research-web.service \
  sapphire-research-hourly.service \
  sapphire-research-hourly.timer \
  sapphire-research-daily.service \
  sapphire-research-daily.timer
do
  if [[ ! -f "$SYSTEMD_DIR/$unit" ]]; then
    echo "missing systemd unit: $SYSTEMD_DIR/$unit" >&2
    exit 1
  fi
done

echo "[1/6] Prepare remote directories"
ssh -o BatchMode=yes "$HOST" "mkdir -p '$REMOTE_ROOT/output' '$REMOTE_ROOT/systemd'"

echo "[2/6] Upload runner + unit files"
scp -q "$RUNNER" "$HOST:$REMOTE_ROOT/research_batch_runner.py"
scp -q "$SYSTEMD_DIR/"* "$HOST:$REMOTE_ROOT/systemd/"

echo "[3/6] Install systemd units"
ssh -o BatchMode=yes "$HOST" "sudo install -m 0644 '$REMOTE_ROOT/systemd/'sapphire-research-*.service /etc/systemd/system/ && sudo install -m 0644 '$REMOTE_ROOT/systemd/'sapphire-research-*.timer /etc/systemd/system/"

echo "[4/6] Retire insecure legacy file server (if present)"
ssh -o BatchMode=yes "$HOST" "sudo systemctl disable --now cluster-dashboard.service >/dev/null 2>&1 || true"

echo "[5/6] Enable/start research services"
ssh -o BatchMode=yes "$HOST" "sudo systemctl daemon-reload && sudo systemctl enable --now sapphire-research-web.service sapphire-research-hourly.timer sapphire-research-daily.timer && sudo systemctl start sapphire-research-hourly.service"

echo "[6/6] Verify"
ssh -o BatchMode=yes "$HOST" "systemctl is-active sapphire-research-web.service sapphire-research-hourly.timer sapphire-research-daily.timer"
sleep 2
curl -sS -m 8 "http://${HOST#*@}:8000/output/latest_hourly.json" | python3 -m json.tool >/dev/null
echo "research endpoint ok: http://${HOST#*@}:8000/output/latest_hourly.json"

echo "Done."
