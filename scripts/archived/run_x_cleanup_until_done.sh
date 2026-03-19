#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/aribs/Sapphire"
STATE="$ROOT/output/x_cleanup/state.json"
LOG_DIR="$ROOT/output/x_cleanup"
LOG_FILE="$LOG_DIR/daemon.log"
LOCK_FILE="$LOG_DIR/daemon.lock"
PID_FILE="$LOG_DIR/daemon.pid"

mkdir -p "$LOG_DIR"

if [[ -f "$LOCK_FILE" ]]; then
  old_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[$(date -u +%FT%TZ)] daemon already running pid=$old_pid" | tee -a "$LOG_FILE"
    exit 0
  fi
fi

echo $$ > "$LOCK_FILE"
echo $$ > "$PID_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

echo "[$(date -u +%FT%TZ)] x-cleanup daemon started" | tee -a "$LOG_FILE"

for i in $(seq 1 200); do
  pending=$(python3 - <<'PY'
import json
from pathlib import Path
p=Path('/Users/aribs/Sapphire/output/x_cleanup/state.json')
if not p.exists():
    print(0)
else:
    s=json.loads(p.read_text())
    print(len(s.get('pending_ids',[])))
PY
)
  deleted=$(python3 - <<'PY'
import json
from pathlib import Path
p=Path('/Users/aribs/Sapphire/output/x_cleanup/state.json')
if not p.exists():
    print(0)
else:
    s=json.loads(p.read_text())
    print(len(s.get('deleted_ids',[])))
PY
)

  echo "[$(date -u +%FT%TZ)] iter=$i pending=$pending deleted=$deleted" | tee -a "$LOG_FILE"

  if [[ "$pending" -le 0 ]]; then
    echo "[$(date -u +%FT%TZ)] queue empty; rescanning once for stragglers" | tee -a "$LOG_FILE"
    python3 "$ROOT/scripts/x_blank_slate_cleanup.py" \
      --env-file "$ROOT/.env.social" \
      --max-scan 1200 \
      --max-rate-limit-retries 1 \
      --max-rate-limit-wait 30 >> "$LOG_FILE" 2>&1 || true

    pending2=$(python3 - <<'PY'
import json
from pathlib import Path
p=Path('/Users/aribs/Sapphire/output/x_cleanup/state.json')
if not p.exists():
    print(0)
else:
    s=json.loads(p.read_text())
    print(len(s.get('pending_ids',[])))
PY
)
    echo "[$(date -u +%FT%TZ)] post-rescan pending=$pending2" | tee -a "$LOG_FILE"
    if [[ "$pending2" -le 0 ]]; then
      echo "[$(date -u +%FT%TZ)] completed: pending_total=0" | tee -a "$LOG_FILE"
      exit 0
    fi
  fi

  python3 "$ROOT/scripts/x_blank_slate_cleanup.py" \
    --env-file "$ROOT/.env.social" \
    --skip-scan \
    --max-delete 10 \
    --delay-seconds 18 \
    --apply >> "$LOG_FILE" 2>&1 || true

done

echo "[$(date -u +%FT%TZ)] reached iteration cap" | tee -a "$LOG_FILE"
