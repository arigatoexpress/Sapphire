#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-rari@100.87.225.89}"
PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_SCRIPT="$LOCAL_ROOT/scripts/telegram_bot_controller.py"
REMOTE_SCRIPT="/home/rari/.openclaw/runtime/codex-projects/scripts/telegram_bot_controller.py"

echo "== Deploy RARI2 Telegram Controller =="
echo "host=$HOST"
echo "project=$PROJECT_ID"

if [[ ! -f "$LOCAL_SCRIPT" ]]; then
  echo "missing script: $LOCAL_SCRIPT" >&2
  exit 1
fi

echo "[1/4] Upload controller script"
scp -q "$LOCAL_SCRIPT" "$HOST:$REMOTE_SCRIPT"

echo "[2/4] Refresh TELEGRAM_BOT_TOKEN + SAPPHIRE_CONTROL_API_TOKEN on Pi env files"
TOKEN_B64="$(gcloud secrets versions access latest --project "$PROJECT_ID" --secret telegram-bot-token | base64 | tr -d '\n')"
CONTROL_B64="$(gcloud secrets versions access latest --project "$PROJECT_ID" --secret SAPPHIRE_CONTROL_API_TOKEN | base64 | tr -d '\n')"
GATEWAY_SIGNAL_URL="${GATEWAY_SIGNAL_URL:-https://sapphire-gateway-267358751314.us-central1.run.app/api/signals/create}"
ssh -o BatchMode=yes "$HOST" "TOKEN_B64='$TOKEN_B64' CONTROL_B64='$CONTROL_B64' GATEWAY_SIGNAL_URL='$GATEWAY_SIGNAL_URL' python3 - <<'PY'
from pathlib import Path
import os
import base64

token = base64.b64decode(os.environ.get('TOKEN_B64', '')).decode().strip()
control = base64.b64decode(os.environ.get('CONTROL_B64', '')).decode().strip()
gateway_signal_url = os.environ.get('GATEWAY_SIGNAL_URL', '').strip()
if not token:
    raise SystemExit('token_missing')
if not control:
    raise SystemExit('control_token_missing')
if not gateway_signal_url:
    raise SystemExit('gateway_signal_url_missing')

targets = [Path('/home/rari/kimi-claw/.env'), Path('/home/rari/kimi-claw-v2/.env')]
for path in targets:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    out = []
    found = False
    found_control = False
    found_gateway = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('TELEGRAM_BOT_TOKEN='):
            out.append(f'TELEGRAM_BOT_TOKEN={token}')
            found = True
        elif stripped.startswith('SAPPHIRE_CONTROL_API_TOKEN='):
            out.append(f'SAPPHIRE_CONTROL_API_TOKEN={control}')
            found_control = True
        elif stripped.startswith('SAPPHIRE_GATEWAY_SIGNAL_URL='):
            out.append(f'SAPPHIRE_GATEWAY_SIGNAL_URL={gateway_signal_url}')
            found_gateway = True
        else:
            out.append(line)
    if not found:
        out.append(f'TELEGRAM_BOT_TOKEN={token}')
    if not found_control:
        out.append(f'SAPPHIRE_CONTROL_API_TOKEN={control}')
    if not found_gateway:
        out.append(f'SAPPHIRE_GATEWAY_SIGNAL_URL={gateway_signal_url}')
    path.write_text('\n'.join(out) + '\n')
print('env_updated', len(targets))
PY"

echo "[3/4] Restart service"
ssh -o BatchMode=yes "$HOST" "sudo systemctl restart telegram-bot-controller.service && sleep 2 && systemctl is-active telegram-bot-controller.service"

echo "[4/4] Verify Telegram token and bot identity (without printing secret)"
cat <<'PY' | ssh -o BatchMode=yes "$HOST" python3
import json
import urllib.request
from pathlib import Path

def token_from_env():
    for path in (Path("/home/rari/kimi-claw/.env"), Path("/home/rari/kimi-claw-v2/.env")):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "TELEGRAM_BOT_TOKEN":
                return v.strip().strip('"').strip("'")
    return ""

token = token_from_env()
print("telegram_token_configured", bool(token))
if not token:
    raise SystemExit(1)

control = ""
gateway = ""
for path in (Path("/home/rari/kimi-claw/.env"), Path("/home/rari/kimi-claw-v2/.env")):
    if not path.exists():
        continue
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key == "SAPPHIRE_CONTROL_API_TOKEN" and not control:
            control = val
        if key == "SAPPHIRE_GATEWAY_SIGNAL_URL" and not gateway:
            gateway = val
print("control_token_configured", bool(control))
print("gateway_signal_url", gateway or "missing")

with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=10) as resp:
    data = json.loads(resp.read().decode())
print("telegram_api_ok", bool(data.get("ok")))
if data.get("ok"):
    print("bot_username", data.get("result", {}).get("username"))
PY

echo "Done."
