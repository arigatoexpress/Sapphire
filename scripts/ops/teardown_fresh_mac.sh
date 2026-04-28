#!/usr/bin/env bash
# Undo files installed by bootstrap_fresh_mac.sh without deleting the repo or
# operator secrets. Dry-run with SAPPHIRE_BOOTSTRAP_DRY_RUN=1.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DRY_RUN="${SAPPHIRE_BOOTSTRAP_DRY_RUN:-0}"
TARGET_REPO="${SAPPHIRE_REPO_PATH:-$HOME/Code/Sapphire}"
LAUNCHAGENTS_DIR="${SAPPHIRE_LAUNCHAGENTS_DIR:-$HOME/Library/LaunchAgents}"
VENV_DIR="${SAPPHIRE_BOOTSTRAP_VENV:-$TARGET_REPO/.venv-fresh-mac}"
RESET_SECRETS="${SAPPHIRE_BOOTSTRAP_RESET_SECRETS:-0}"
SECRETS_FILE="${SAPPHIRE_SECRETS_FILE:-$HOME/.sapphire/secrets.env}"

say() {
  printf '%s\n' "$*"
}

run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

remove_demo_launchagents() {
  list_file="$TARGET_REPO/infra/bootstrap/demo-launchagents.list"
  [ -f "$list_file" ] || list_file="$REPO_ROOT/infra/bootstrap/demo-launchagents.list"
  if [ ! -f "$list_file" ]; then
    say "launchagents: no demo list found, nothing to remove"
    return 0
  fi

  while IFS= read -r relpath || [ -n "$relpath" ]; do
    case "$relpath" in
      ''|\#*) continue ;;
    esac
    dest="$LAUNCHAGENTS_DIR/$(basename "$relpath")"
    if [ -f "$dest" ]; then
      run rm -f "$dest"
    fi
  done < "$list_file"
}

remove_venv() {
  if [ -d "$VENV_DIR" ]; then
    run rm -rf "$VENV_DIR"
  fi
}

maybe_remove_placeholder_secrets() {
  if [ "$RESET_SECRETS" != "1" ]; then
    say "secrets: preserved $SECRETS_FILE (set SAPPHIRE_BOOTSTRAP_RESET_SECRETS=1 to remove placeholder file)"
    return 0
  fi
  if [ -f "$SECRETS_FILE" ] && grep -q "PLACEHOLDER_DO_NOT_USE" "$SECRETS_FILE"; then
    run rm -f "$SECRETS_FILE"
    say "secrets: removed placeholder demo secrets"
  else
    say "secrets: preserved non-placeholder or missing secrets file"
  fi
}

main() {
  remove_demo_launchagents
  remove_venv
  maybe_remove_placeholder_secrets
  say "fresh-mac demo teardown complete"
}

main "$@"
