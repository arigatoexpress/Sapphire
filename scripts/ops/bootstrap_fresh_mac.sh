#!/usr/bin/env bash
# Bootstrap a fresh macOS workstation into a demo-safe Sapphire checkout.
#
# Default mode is demo-safe: placeholder secrets, no live external APIs, and
# LaunchAgents copied with RunAtLoad=false. Set SAPPHIRE_BOOTSTRAP_DRY_RUN=1 to
# trace commands without writing outside the current repo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DRY_RUN="${SAPPHIRE_BOOTSTRAP_DRY_RUN:-0}"
DEMO_MODE="${SAPPHIRE_BOOTSTRAP_DEMO_MODE:-1}"
REPO_URL="${SAPPHIRE_REPO_URL:-https://github.com/arigatoexpress/Sapphire.git}"
TARGET_REPO="${SAPPHIRE_REPO_PATH:-$HOME/Code/Sapphire}"
VENV_DIR="${SAPPHIRE_BOOTSTRAP_VENV:-$TARGET_REPO/.venv-fresh-mac}"
SECRETS_DIR="${SAPPHIRE_SECRETS_DIR:-$HOME/.sapphire}"
SECRETS_FILE="${SAPPHIRE_SECRETS_FILE:-$SECRETS_DIR/secrets.env}"
LAUNCHAGENTS_DIR="${SAPPHIRE_LAUNCHAGENTS_DIR:-$HOME/Library/LaunchAgents}"
LOG_DIR="${SAPPHIRE_LOG_DIR:-$HOME/Library/Logs/sapphire}"
AUTONOMY_LOG_DIR="${SAPPHIRE_AUTONOMY_LOG_DIR:-$HOME/autonomy-status/logs}"
PYTHON_BIN="${SAPPHIRE_BOOTSTRAP_PYTHON:-}"
LOCAL_CI_SMOKE="${SAPPHIRE_BOOTSTRAP_LOCAL_CI_SMOKE:-1}"

say() {
  printf '%s\n' "$*"
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

trace() {
  printf '[dry-run] %s\n' "$*"
}

run() {
  if [ "$DRY_RUN" = "1" ]; then
    trace "$*"
    return 0
  fi
  "$@"
}

need_demo_mode() {
  [ "$DEMO_MODE" = "1" ] || die "fresh-mac bootstrap only supports demo mode by default; set up secrets manually before live mode"
}

detect_platform() {
  os_name="$(uname -s)"
  case "$os_name" in
    Darwin)
      say "platform: macOS"
      ;;
    Linux)
      say "platform: Linux fallback"
      say "note: LaunchAgents are macOS-only; this run will skip plist installation."
      ;;
    *)
      die "unsupported platform: $os_name"
      ;;
  esac
}

install_or_validate_brew_tools() {
  os_name="$(uname -s)"
  if [ "$os_name" != "Darwin" ]; then
    say "brew: skipped on non-macOS; install git, python3, ruff, and gitleaks with your package manager"
    return 0
  fi

  if ! command -v brew >/dev/null 2>&1; then
    if [ "$DRY_RUN" = "1" ]; then
      trace "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
      return 0
    fi
    die "Homebrew is required. Install it first, then rerun this bootstrap."
  fi

  if [ "$DRY_RUN" = "1" ]; then
    for tool in git python@3.11 ruff gitleaks; do
      trace "brew list $tool || brew install $tool"
    done
    return 0
  fi

  for tool in git python@3.11 ruff gitleaks; do
    if brew list "$tool" >/dev/null 2>&1; then
      say "brew: $tool already installed"
    else
      run brew install "$tool"
    fi
  done
}

ensure_checkout() {
  if [ -d "$TARGET_REPO/.git" ]; then
    say "repo: existing checkout at $TARGET_REPO"
    run git -C "$TARGET_REPO" fetch origin main
  elif [ -d "$TARGET_REPO" ]; then
    die "$TARGET_REPO exists but is not a git checkout"
  else
    run mkdir -p "$(dirname "$TARGET_REPO")"
    run git clone "$REPO_URL" "$TARGET_REPO"
  fi
}

resolve_python() {
  if [ -n "$PYTHON_BIN" ]; then
    printf '%s\n' "$PYTHON_BIN"
  elif [ -x /usr/local/bin/python3 ]; then
    printf '%s\n' /usr/local/bin/python3
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die "python3 not found"
  fi
}

ensure_venv_and_test_requirements() {
  py="$(resolve_python)"
  say "python: $py"
  run "$py" -m venv "$VENV_DIR"
  run "$VENV_DIR/bin/python" -m pip install --upgrade pip
  run "$VENV_DIR/bin/python" -m pip install -r "$TARGET_REPO/requirements-test.txt"
}

ensure_demo_secrets() {
  template="$TARGET_REPO/infra/secrets.env.example"
  if [ ! -f "$template" ]; then
    template="$REPO_ROOT/infra/secrets.env.example"
  fi
  [ -f "$template" ] || die "missing secrets template: $template"

  run mkdir -p "$SECRETS_DIR"
  if [ -f "$SECRETS_FILE" ]; then
    say "secrets: existing $SECRETS_FILE preserved"
  else
    run cp "$template" "$SECRETS_FILE"
    run chmod 600 "$SECRETS_FILE"
    say "secrets: wrote demo placeholders to $SECRETS_FILE"
  fi
}

plist_runatload_false() {
  src="$1"
  dest="$2"
  repo_for_plist="$3"
  if [ "$DRY_RUN" = "1" ]; then
    trace "install plist $(basename "$src") with RunAtLoad=false -> $dest"
    return 0
  fi
  python3 - "$src" "$dest" "$repo_for_plist" <<'PY'
import plistlib
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dest = Path(sys.argv[2])
repo = sys.argv[3]
payload = plistlib.loads(src.read_bytes())
payload["RunAtLoad"] = False
env = dict(payload.get("EnvironmentVariables", {}))
env.update(
    {
        "SAPPHIRE_DEMO_MODE": "1",
        "SAPPHIRE_LIVE_MODE": "0",
        "SAPPHIRE_DISABLE_EXTERNAL_APIS": "1",
        "TELEGRAM_DRY_RUN": "1",
        "TRADINGVIEW_EXECUTION_ENABLED": "false",
        "SAPPHIRE_TRADING_LIVE": "0",
        "SAPPHIRE_ROBINHOOD_LIVE": "0",
        "SAPPHIRE_HYPERLIQUID_LIVE": "0",
        "SAPPHIRE_X402_LIVE": "0",
        "X402_ENABLED": "0",
        "SAPPHIRE_PUBLISH_LIVE": "0",
    }
)
payload["EnvironmentVariables"] = env
for key in ("WorkingDirectory", "StandardOutPath", "StandardErrorPath"):
    value = payload.get(key)
    if isinstance(value, str):
        payload[key] = re.sub(r"/Users/[^/]+/Code/Sapphire", repo, value)
dest.write_bytes(plistlib.dumps(payload, sort_keys=True))
PY
  chmod 644 "$dest"
}

install_demo_launchagents() {
  os_name="$(uname -s)"
  if [ "$os_name" != "Darwin" ]; then
    say "launchagents: skipped on non-macOS"
    return 0
  fi

  list_file="$TARGET_REPO/infra/bootstrap/demo-launchagents.list"
  [ -f "$list_file" ] || list_file="$REPO_ROOT/infra/bootstrap/demo-launchagents.list"
  [ -f "$list_file" ] || die "missing launchagent list: $list_file"

  run mkdir -p "$LAUNCHAGENTS_DIR" "$LOG_DIR" "$AUTONOMY_LOG_DIR"
  while IFS= read -r relpath || [ -n "$relpath" ]; do
    case "$relpath" in
      ''|\#*) continue ;;
    esac
    src="$TARGET_REPO/$relpath"
    [ -f "$src" ] || src="$REPO_ROOT/$relpath"
    [ -f "$src" ] || die "missing LaunchAgent template: $relpath"
    dest="$LAUNCHAGENTS_DIR/$(basename "$src")"
    plist_runatload_false "$src" "$dest" "$TARGET_REPO"
  done < "$list_file"
  say "launchagents: copied demo plists with RunAtLoad=false; not bootstrapped"
}

smoke_verify_local_ci() {
  if [ "$LOCAL_CI_SMOKE" != "1" ]; then
    say "local-ci: skipped by SAPPHIRE_BOOTSTRAP_LOCAL_CI_SMOKE=$LOCAL_CI_SMOKE"
    return 0
  fi
  run "$VENV_DIR/bin/python" "$TARGET_REPO/scripts/ops/local_ci_verify.py" \
    --skip-plugin \
    --skip-registry \
    --skip-test-inventory \
    --quiet
}

main() {
  need_demo_mode
  detect_platform
  install_or_validate_brew_tools
  ensure_checkout
  ensure_venv_and_test_requirements
  ensure_demo_secrets
  install_demo_launchagents
  smoke_verify_local_ci
  say "fresh-mac bootstrap complete (demo-safe)"
}

main "$@"
