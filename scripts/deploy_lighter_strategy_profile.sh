#!/usr/bin/env bash
set -euo pipefail

# Deploy a named strategy profile to the rari2 Lighter bot (.env + restart).
# Usage:
#   scripts/deploy_lighter_strategy_profile.sh [profile] [host]
#
# Profiles:
#   luxalgo_sol_15m_safe    (default)
#   luxalgo_sol_5m_active
#   chartprime_sol_5m_test

PROFILE="${1:-luxalgo_sol_15m_safe}"
TARGET_HOST="${2:-rari@100.87.225.89}"
ENV_FILE="/home/rari/Sapphire/services/bot-lighter/.env"
SERVICE="lighter-trading"

declare -A KV

case "$PROFILE" in
  luxalgo_sol_15m_safe)
    KV[LIGHTER_ALLOWED_STRATEGIES]="luxalgo_msb_ob,smart_money_breakout,algoalpha_smb"
    KV[LIGHTER_ALLOWED_TIMEFRAMES]="15m"
    KV[LIGHTER_STRATEGY_REQUIRE_METADATA]="true"
    KV[LIGHTER_SINGLE_SYMBOL_MODE]="true"
    KV[LIGHTER_MAX_ORDER_NOTIONAL_USD]="4"
    KV[LIGHTER_MAX_POSITION_NOTIONAL_USD]="4"
    KV[LIGHTER_TARGET_ORDER_NOTIONAL_USD]="4"
    KV[LIGHTER_MAX_SIGNAL_LEVERAGE]="20"
    KV[LIGHTER_ENTRY_COOLDOWN_SECONDS]="600"
    KV[LIGHTER_DEFAULT_TAKE_PROFIT_PCT]="1.2"
    KV[LIGHTER_DEFAULT_STOP_LOSS_PCT]="0.8"
    KV[LIGHTER_PROGRESS_VERIFY_INTERVAL_SECONDS]="120"
    KV[LIGHTER_MAX_DRAWDOWN_ALERT_PCT]="6"
    KV[LIGHTER_DRAWDOWN_ALERT_COOLDOWN_SECONDS]="900"
    KV[LIGHTER_SYNC_STALE_ALERT_SECONDS]="300"
    KV[LIGHTER_SYNC_STALE_ALERT_COOLDOWN_SECONDS]="900"
    ;;
  luxalgo_sol_5m_active)
    KV[LIGHTER_ALLOWED_STRATEGIES]="luxalgo_msb_ob,smart_money_breakout,algoalpha_smb"
    KV[LIGHTER_ALLOWED_TIMEFRAMES]="5m"
    KV[LIGHTER_STRATEGY_REQUIRE_METADATA]="true"
    KV[LIGHTER_SINGLE_SYMBOL_MODE]="true"
    KV[LIGHTER_MAX_ORDER_NOTIONAL_USD]="4"
    KV[LIGHTER_MAX_POSITION_NOTIONAL_USD]="4"
    KV[LIGHTER_TARGET_ORDER_NOTIONAL_USD]="4"
    KV[LIGHTER_MAX_SIGNAL_LEVERAGE]="20"
    KV[LIGHTER_ENTRY_COOLDOWN_SECONDS]="180"
    KV[LIGHTER_DEFAULT_TAKE_PROFIT_PCT]="1.2"
    KV[LIGHTER_DEFAULT_STOP_LOSS_PCT]="0.8"
    KV[LIGHTER_PROGRESS_VERIFY_INTERVAL_SECONDS]="120"
    KV[LIGHTER_MAX_DRAWDOWN_ALERT_PCT]="7"
    KV[LIGHTER_DRAWDOWN_ALERT_COOLDOWN_SECONDS]="900"
    KV[LIGHTER_SYNC_STALE_ALERT_SECONDS]="300"
    KV[LIGHTER_SYNC_STALE_ALERT_COOLDOWN_SECONDS]="900"
    ;;
  chartprime_sol_5m_test)
    KV[LIGHTER_ALLOWED_STRATEGIES]="chartprime_tbt,trendline_breakout_targets"
    KV[LIGHTER_ALLOWED_TIMEFRAMES]="5m"
    KV[LIGHTER_STRATEGY_REQUIRE_METADATA]="true"
    KV[LIGHTER_SINGLE_SYMBOL_MODE]="true"
    KV[LIGHTER_MAX_ORDER_NOTIONAL_USD]="4"
    KV[LIGHTER_MAX_POSITION_NOTIONAL_USD]="4"
    KV[LIGHTER_TARGET_ORDER_NOTIONAL_USD]="4"
    KV[LIGHTER_MAX_SIGNAL_LEVERAGE]="20"
    KV[LIGHTER_ENTRY_COOLDOWN_SECONDS]="300"
    KV[LIGHTER_DEFAULT_TAKE_PROFIT_PCT]="1.0"
    KV[LIGHTER_DEFAULT_STOP_LOSS_PCT]="0.7"
    KV[LIGHTER_PROGRESS_VERIFY_INTERVAL_SECONDS]="120"
    KV[LIGHTER_MAX_DRAWDOWN_ALERT_PCT]="5"
    KV[LIGHTER_DRAWDOWN_ALERT_COOLDOWN_SECONDS]="900"
    KV[LIGHTER_SYNC_STALE_ALERT_SECONDS]="300"
    KV[LIGHTER_SYNC_STALE_ALERT_COOLDOWN_SECONDS]="900"
    ;;
  *)
    echo "Unknown profile: $PROFILE" >&2
    exit 1
    ;;
esac

echo "Applying profile '$PROFILE' to $TARGET_HOST ..."

# Build Python dict literal content safely.
UPDATES_PY=""
for k in "${!KV[@]}"; do
  v="${KV[$k]}"
  UPDATES_PY="${UPDATES_PY}    '${k}': '${v}',"$'\n'
done

ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET_HOST" "python3 - <<'PY'
from pathlib import Path

env_file = Path('${ENV_FILE}')
lines = env_file.read_text().splitlines() if env_file.exists() else []
updates = {
${UPDATES_PY}}

out = []
seen = set()
for ln in lines:
    if '=' in ln and not ln.strip().startswith('#'):
        key, _ = ln.split('=', 1)
        k = key.strip()
        if k in updates:
            out.append(f\"{k}={updates[k]}\")
            seen.add(k)
            continue
    out.append(ln)

for k, v in updates.items():
    if k not in seen:
        out.append(f\"{k}={v}\")

env_file.write_text('\\n'.join(out) + '\\n')
print(f'Updated {env_file}')
for k in sorted(updates):
    print(f'{k}={updates[k]}')
PY"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET_HOST" \
  "sudo systemctl reset-failed ${SERVICE} || true; \
   sudo systemctl restart ${SERVICE} || { \
     sudo systemctl reset-failed ${SERVICE} || true; \
     sudo systemctl start ${SERVICE}; \
   }; \
   sleep 8; \
   systemctl is-active ${SERVICE}; \
   journalctl -u ${SERVICE} -n 50 --no-pager"

echo
echo "Profile '${PROFILE}' deployed."
