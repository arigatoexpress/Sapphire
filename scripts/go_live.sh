#!/usr/bin/env bash
# Sapphire OS — One-shot "flip everything live" script.
#
# Chains the steps Ari would otherwise run by hand after filling in
# .env.integrations:
#
#   1. chmod 600 .env.integrations               (refuses to continue otherwise)
#   2. scripts/load_integrations_env.sh          (launchd bridge)
#   3. scripts/smoke_integrations.py             (confirm all configured probes PASS)
#   4. python3 -m lib.content.auto_publish --once --dry-run
#                                                (publisher previews, nothing leaves)
#   5. PROMPT: flip SAPPHIRE_PUBLISH_LIVE=1
#   6. python3 -m lib.content.auto_publish --once
#                                                (first live publish, manual trigger)
#   7. launchctl load ~/Library/LaunchAgents/com.sapphire.content-publisher.plist
#                                                (6:15 AM daily cron)
#
# Between steps 4 and 5, and between 5 and 6, the script prompts for
# explicit "yes" confirmation. Every step before that aborts on error.
#
# Usage:
#   scripts/go_live.sh              # full sequence
#   scripts/go_live.sh --rollback   # flip LIVE=0 and unload LaunchAgent
#   scripts/go_live.sh --dry-only   # stop after step 4; never ask to go live
#
# Exit codes:
#   0  finished without errors (either completed or user declined live flip)
#   1  prerequisite failure (file missing, perms wrong, smoke failed, etc.)
#   2  user aborted at a confirmation gate

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="$REPO_ROOT/.env.integrations"
LAUNCH_PLIST="$HOME/Library/LaunchAgents/com.sapphire.content-publisher.plist"
PYTHON="${SAPPHIRE_PYTHON:-/usr/local/bin/python3}"

# ANSI (only if stdout is a tty)
if [ -t 1 ]; then
    BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"
    OK="$(printf '\033[32m')"; WARN="$(printf '\033[33m')"
    ERR="$(printf '\033[31m')"; RESET="$(printf '\033[0m')"
else
    BOLD=""; DIM=""; OK=""; WARN=""; ERR=""; RESET=""
fi

step() { echo; echo "${BOLD}── $* ──${RESET}"; }
ok()   { echo "${OK}✓${RESET} $*"; }
warn() { echo "${WARN}!${RESET} $*"; }
fail() { echo "${ERR}✗ $*${RESET}" >&2; exit "${2:-1}"; }

confirm() {
    local prompt="$1"
    local answer
    read -r -p "${BOLD}${prompt}${RESET} (type 'yes' to proceed): " answer
    [[ "$answer" == "yes" ]] || { warn "aborted at confirmation gate"; exit 2; }
}

# ------------------------------ rollback path ----------------------------

if [[ "${1:-}" == "--rollback" ]]; then
    step "Rollback: disable live publishing"
    launchctl setenv SAPPHIRE_PUBLISH_LIVE 0 && ok "SAPPHIRE_PUBLISH_LIVE=0"
    if launchctl list | grep -q com.sapphire.content-publisher; then
        launchctl unload "$LAUNCH_PLIST" && ok "LaunchAgent unloaded"
    else
        warn "LaunchAgent was not loaded; nothing to unload"
    fi
    echo
    ok "Rollback complete. Publisher is dry-run; cron is off."
    exit 0
fi

DRY_ONLY=0
[[ "${1:-}" == "--dry-only" ]] && DRY_ONLY=1

# ------------------------------ pre-flight -------------------------------

step "Pre-flight: env file + permissions"

[[ -f "$ENV_FILE" ]] || fail "missing $ENV_FILE — copy .env.integrations.example and fill values before running this"

# Enforce chmod 600
chmod 600 "$ENV_FILE"
perms="$(stat -f '%A' "$ENV_FILE" 2>/dev/null || stat -c '%a' "$ENV_FILE")"
[[ "$perms" == "600" ]] || fail "permissions on $ENV_FILE are $perms; must be 600"
ok "env file found, mode 600"

# Verify python
command -v "$PYTHON" >/dev/null 2>&1 || fail "python not found at $PYTHON (override with SAPPHIRE_PYTHON=)"
ok "python: $("$PYTHON" --version 2>&1)"

# ------------------------------ step 2 -----------------------------------

step "Step 2/7: Load env into launchd"
bash scripts/load_integrations_env.sh || fail "load_integrations_env.sh failed"
ok "env loaded into launchd GUI session"

# ------------------------------ step 3 -----------------------------------

step "Step 3/7: Smoke test all integrations"
if "$PYTHON" scripts/smoke_integrations.py; then
    ok "smoke PASS (all configured probes green)"
else
    rc=$?
    fail "smoke_integrations.py exited $rc — fix failures before going live" $rc
fi

# ------------------------------ step 4 -----------------------------------

step "Step 4/7: Publisher dry-run"
if "$PYTHON" -m lib.content.auto_publish --once --dry-run; then
    ok "dry-run complete — request previews in data/content/ready/"
else
    fail "dry-run failed; check lib.content.auto_publish output"
fi

if [[ "$DRY_ONLY" == "1" ]]; then
    echo
    ok "--dry-only requested; stopping here. Re-run without --dry-only to go live."
    exit 0
fi

# ------------------------------ step 5 gate ------------------------------

step "Step 5/7: Flip SAPPHIRE_PUBLISH_LIVE → 1"
echo "${DIM}This is the irreversible-until-rollback flip. Content will actually post on next run.${RESET}"
echo "${DIM}Rollback: scripts/go_live.sh --rollback${RESET}"
confirm "Flip SAPPHIRE_PUBLISH_LIVE to 1 now?"

launchctl setenv SAPPHIRE_PUBLISH_LIVE 1
ok "SAPPHIRE_PUBLISH_LIVE=1 in launchd GUI session"

# ------------------------------ step 6 -----------------------------------

step "Step 6/7: First live publish"
echo "${DIM}Next call will actually send to LinkedIn/X/Substack-via-Resend (whichever are configured).${RESET}"
confirm "Run auto_publish --once for real?"

if "$PYTHON" -m lib.content.auto_publish --once; then
    ok "live publish completed — check LinkedIn/X/Substack inbox for the landing"
else
    rc=$?
    warn "auto_publish returned $rc — check data/content/published/ for results, may be partial"
fi

# ------------------------------ step 7 -----------------------------------

step "Step 7/7: Load the 6:15 AM LaunchAgent"
[[ -f "$LAUNCH_PLIST" ]] || fail "missing $LAUNCH_PLIST"

if launchctl list | grep -q com.sapphire.content-publisher; then
    warn "LaunchAgent already loaded; unloading first to pick up new env"
    launchctl unload "$LAUNCH_PLIST" || true
fi
launchctl load "$LAUNCH_PLIST" && ok "LaunchAgent loaded — next fire 6:15 AM CT"

# ------------------------------ done -------------------------------------

echo
echo "${BOLD}${OK}✓ Sapphire content engine is LIVE.${RESET}"
echo
echo "Next fire:  6:15 AM CT tomorrow"
echo "Logs:       ~/Library/Logs/sapphire/"
echo "Rollback:   scripts/go_live.sh --rollback"
echo "Dashboard:  http://localhost:8080  (AUTH_PASSWORD=sapphire)"
