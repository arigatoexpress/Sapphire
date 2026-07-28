#!/usr/bin/env bash
# Restore Sapphire LaunchAgents to ~/Library/LaunchAgents and bootstrap them.
#
# CONTEXT (audit 2026-07-25): all 33 tracked plists in infra/launchagents/ were
# absent from ~/Library/LaunchAgents, and launchctl held 45 residual
# "disabled" override records. Zero Sapphire agents were loaded. The plists
# themselves are valid (plutil-lint clean, all interpreter/script paths
# resolve) — they were simply never (re)deployed.
#
# Tiers exist because loading an agent STARTS it. Read before running.
#
#   infra   — services + housekeeping. No market actions, no outward sends.
#   intel   — scheduled read/analysis jobs. Network reads; morning-brief sends
#             to Telegram (self-DM), which is an inward notification.
#   trading — signal/execution loops. auto-executor is PAPER_TRADING=1, but
#             these drive the live trading path. Deliberate opt-in only.
#   publish — com.sapphire.content-publisher runs lib.content.auto_publish,
#             which posts OUTWARD to Substack/X/LinkedIn. NOT included in
#             'all'. Must be named explicitly, and only after you have
#             confirmed the approval queue is behaving.
#
# Usage:
#   scripts/ops/restore_launchagents.sh --list
#   scripts/ops/restore_launchagents.sh --dry-run infra
#   scripts/ops/restore_launchagents.sh infra
#   scripts/ops/restore_launchagents.sh intel trading
#   scripts/ops/restore_launchagents.sh all          # infra + intel + trading
#   scripts/ops/restore_launchagents.sh publish      # outward — explicit only
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO/infra/launchagents"
DEST="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"

# Plists live in TWO places. infra/launchagents/ holds the shared fleet;
# service-owned agents ship next to their code under services/*/launchagent/.
# This script used to glob only the former, so `--all` silently skipped
# com.sapphire.{dashboard,inference-proxy,pm-bot} — they showed up in the
# readiness sweep as "not loaded" and were mistaken for stale checks.
# resolve_plist() looks in both.
resolve_plist() {
  local label="$1"
  if [ -f "$SRC/$label.plist" ]; then
    printf '%s\n' "$SRC/$label.plist"
    return 0
  fi
  local candidate
  for candidate in "$REPO"/services/*/launchagent/"$label.plist"; do
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

INFRA=(control-plane openbb-api heartbeat logrotate telemetry-collector
       dashboard inference-proxy service-supervisor)
# service-supervisor lives under services/service_supervisor/launchagent/ and
# fires every 60s to self-heal downed Sapphire services; keeping it in `infra`
# means `--all` restores the watchdog whenever the fleet gets brought back up.
INTEL=(chain-refresh correlation-refresh threat-refresh market-intel
       continuous-intelligence-daily morning-brief morning-digest
       gemini-ooda-daily telegram-intel-reader
       fleet-status readiness-cache security-pipeline tdr-pro-sync
       foundry-sync gcp-sync backtest-weekly self-optimization
       lead-pipeline content-engine)
# morning-digest and telegram-intel-reader also live under services/*/launchagent/.
# morning-digest writes an 8 AM local draft (PM-bot reviewed, never sends direct).
# telegram-intel-reader is a READER daemon that no-ops unless
# SAPPHIRE_TELEGRAM_INTEL_LIVE=1 + config files are present, so restoring it in
# batch is safe — it exits clean without live config, and does not send outward.
TRADING=(signal-logger alpha-agent auto-executor trading-shadow-controller
         webhook-receiver-mac webhook-tunnel tv-webhook-url-sync
         tradingview-cdp tradingview-ta-capture tradingview-pine-batch)
PUBLISH=(content-publisher)
# com.sapphire.pm-bot owns Telegram ingress. Excluded from 'all' on purpose:
# its committed plist sets MODE=polling + SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING=1,
# which contradicts the documented policy (webhook mode, shared-token polling
# disabled — CLAUDE.md "Telegram PM Bot"). Reconcile that before loading it,
# or you risk a poller conflict with the Windows bot.
TELEGRAM=(pm-bot)

DRY_RUN=0
SELECTED=()

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --list)
      printf 'infra:    %s\n\n' "${INFRA[*]}"
      printf 'intel:    %s\n\n' "${INTEL[*]}"
      printf 'trading:  %s\n\n' "${TRADING[*]}"
      printf 'telegram: %s  (Telegram ingress — explicit only)\n\n' "${TELEGRAM[*]}"
      printf 'publish:  %s  (OUTWARD — posts publicly)\n' "${PUBLISH[*]}"
      exit 0 ;;
    infra)    SELECTED+=("${INFRA[@]}") ;;
    intel)    SELECTED+=("${INTEL[@]}") ;;
    trading)  SELECTED+=("${TRADING[@]}") ;;
    telegram) SELECTED+=("${TELEGRAM[@]}") ;;
    publish)  SELECTED+=("${PUBLISH[@]}") ;;
    all)      SELECTED+=("${INFRA[@]}" "${INTEL[@]}" "${TRADING[@]}") ;;
    *) echo "unknown tier: $arg (want: infra|intel|trading|telegram|publish|all)" >&2; exit 2 ;;
  esac
done

if [ ${#SELECTED[@]} -eq 0 ]; then
  echo "no tier selected. try --list" >&2
  exit 2
fi

mkdir -p "$DEST"
loaded=0; skipped=0

for name in "${SELECTED[@]}"; do
  label="com.sapphire.$name"

  if ! plist="$(resolve_plist "$label")"; then
    echo "  SKIP  $label — no plist in infra/launchagents/ or services/*/launchagent/"
    skipped=$((skipped + 1))
    continue
  fi
  if ! plutil -lint "$plist" >/dev/null 2>&1; then
    echo "  SKIP  $label — plutil lint failed"
    skipped=$((skipped + 1))
    continue
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  DRY   $label → would copy + enable + bootstrap"
    continue
  fi

  cp "$plist" "$DEST/$label.plist"
  # Clear the residual disabled-override, else bootstrap is a no-op.
  launchctl enable "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  if launchctl bootstrap "$DOMAIN" "$DEST/$label.plist" 2>/dev/null; then
    echo "  OK    $label"
    loaded=$((loaded + 1))
  else
    echo "  FAIL  $label — bootstrap rejected (check data/logs/)"
    skipped=$((skipped + 1))
  fi
done

if [ "$DRY_RUN" -eq 0 ]; then
  echo
  echo "loaded=$loaded skipped=$skipped"
  echo "verify:  launchctl list | grep sapphire"
  echo "a non-zero exit code in column 2 means the job ran and failed."
fi
