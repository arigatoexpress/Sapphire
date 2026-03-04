#!/usr/bin/env bash
set -euo pipefail

# Defensive integration wrapper for Shannon (autonomous pentest).
# Runs only against explicitly authorized and allowlisted targets by default.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TARGET_URL="${TARGET_URL:-${1:-}}"
TARGET_REPO_PATH="${TARGET_REPO_PATH:-$ROOT_DIR}"
TARGET_REPO_NAME="${TARGET_REPO_NAME:-$(basename "$TARGET_REPO_PATH")}"

SHANNON_HOME="${SHANNON_HOME:-$ROOT_DIR/tools/shannon}"
SHANNON_OUTPUT_DIR="${SHANNON_OUTPUT_DIR:-$ROOT_DIR/output/security/shannon}"
SHANNON_WORKSPACE="${SHANNON_WORKSPACE:-}"
SHANNON_CONFIG_SOURCE="${SHANNON_CONFIG_SOURCE:-}"

ALLOWLIST_FILE="${SHANNON_ALLOWED_HOSTS_FILE:-$ROOT_DIR/configs/security/shannon-target-allowlist.txt}"
DENYLIST_FILE="${SHANNON_PRODUCTION_DENYLIST_FILE:-$ROOT_DIR/configs/security/shannon-production-denylist.txt}"

SHANNON_ALLOW_PRODUCTION="${SHANNON_ALLOW_PRODUCTION:-false}"
AUTHORIZATION_ACK="${AUTHORIZATION_ACK:-}"
SHANNON_SKIP_UPDATE="${SHANNON_SKIP_UPDATE:-false}"

usage() {
  cat <<'EOF'
Usage:
  TARGET_URL=https://staging.example.com \
  TARGET_REPO_PATH=/path/to/repo \
  AUTHORIZATION_ACK=I_HAVE_EXPLICIT_AUTHORIZATION \
  ./scripts/run_shannon_scan.sh

Optional env:
  TARGET_REPO_NAME=<repo-name>                    # default basename(TARGET_REPO_PATH)
  SHANNON_HOME=<path>                             # default ./tools/shannon
  SHANNON_OUTPUT_DIR=<path>                       # default ./output/security/shannon
  SHANNON_WORKSPACE=<name>                        # default generated
  SHANNON_CONFIG_SOURCE=<path-to-yaml>            # optional auth/rules config
  SHANNON_ALLOW_PRODUCTION=true                   # required for denylisted hosts
  SHANNON_ALLOWED_HOSTS_FILE=<path>               # default configs/security/shannon-target-allowlist.txt
  SHANNON_PRODUCTION_DENYLIST_FILE=<path>         # default configs/security/shannon-production-denylist.txt
  SHANNON_SKIP_UPDATE=true                        # skip git pull for Shannon checkout
EOF
}

if [[ -z "$TARGET_URL" || "$TARGET_URL" == "-h" || "$TARGET_URL" == "--help" ]]; then
  usage
  exit 1
fi

if [[ "$AUTHORIZATION_ACK" != "I_HAVE_EXPLICIT_AUTHORIZATION" ]]; then
  echo "ERROR: AUTHORIZATION_ACK must be exactly 'I_HAVE_EXPLICIT_AUTHORIZATION'."
  echo "Refusing to run autonomous exploitation without explicit acknowledgement."
  exit 2
fi

if [[ ! -d "$TARGET_REPO_PATH" ]]; then
  echo "ERROR: TARGET_REPO_PATH does not exist: $TARGET_REPO_PATH"
  exit 3
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required."
  exit 4
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required."
  exit 5
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync is required."
  exit 6
fi

host="${TARGET_URL#*://}"
host="${host%%/*}"
host="${host%%:*}"
if [[ -z "$host" ]]; then
  echo "ERROR: Could not parse host from TARGET_URL=$TARGET_URL"
  exit 7
fi

matches_pattern_file() {
  local value="$1"
  local file="$2"
  [[ -f "$file" ]] || return 1
  while IFS= read -r raw; do
    local pattern="${raw%%#*}"
    pattern="$(echo "$pattern" | xargs || true)"
    [[ -z "$pattern" ]] && continue
    if [[ "$value" == $pattern ]]; then
      return 0
    fi
  done <"$file"
  return 1
}

if [[ -f "$ALLOWLIST_FILE" ]]; then
  if ! matches_pattern_file "$host" "$ALLOWLIST_FILE"; then
    echo "ERROR: Target host '$host' is not allowlisted in $ALLOWLIST_FILE"
    exit 8
  fi
fi

if [[ "$SHANNON_ALLOW_PRODUCTION" != "true" && -f "$DENYLIST_FILE" ]]; then
  if matches_pattern_file "$host" "$DENYLIST_FILE"; then
    echo "ERROR: Target host '$host' is denylisted in $DENYLIST_FILE"
    echo "Set SHANNON_ALLOW_PRODUCTION=true only if you intentionally approved this."
    exit 9
  fi
fi

if [[ -n "$SHANNON_CONFIG_SOURCE" && "$SHANNON_CONFIG_SOURCE" != /* ]]; then
  SHANNON_CONFIG_SOURCE="$ROOT_DIR/$SHANNON_CONFIG_SOURCE"
fi

mkdir -p "$(dirname "$SHANNON_HOME")"
if [[ ! -d "$SHANNON_HOME/.git" ]]; then
  git clone --depth 1 https://github.com/KeygraphHQ/shannon.git "$SHANNON_HOME"
elif [[ "$SHANNON_SKIP_UPDATE" != "true" ]]; then
  git -C "$SHANNON_HOME" pull --ff-only || true
fi

mkdir -p "$SHANNON_OUTPUT_DIR"
mkdir -p "$SHANNON_HOME/repos"

# Shannon expects source under ./repos/<REPO>.
# Use printf (not echo) so trailing newline doesn't become a trailing '-'.
safe_repo_name="$(
  printf '%s' "$TARGET_REPO_NAME" \
    | tr -cs '[:alnum:]_-' '-' \
    | sed -E 's/^-+//; s/-+$//'
)"
if [[ -z "$safe_repo_name" ]]; then
  echo "ERROR: TARGET_REPO_NAME resolved to an empty safe repo name."
  exit 11
fi
scan_repo_dir="$SHANNON_HOME/repos/$safe_repo_name"
mkdir -p "$scan_repo_dir"
rsync -a \
  --exclude "node_modules" \
  --exclude ".venv" \
  --exclude ".pytest_cache" \
  --exclude "output" \
  "$TARGET_REPO_PATH"/ "$scan_repo_dir"/

# Preflight requires a git repository. If the source path has no .git folder
# (or was synced without it), initialize a local repo in-place.
if [[ ! -d "$scan_repo_dir/.git" ]]; then
  git -C "$scan_repo_dir" init >/dev/null 2>&1 || true
fi

config_arg=""
if [[ -n "$SHANNON_CONFIG_SOURCE" ]]; then
  if [[ ! -f "$SHANNON_CONFIG_SOURCE" ]]; then
    echo "ERROR: SHANNON_CONFIG_SOURCE not found: $SHANNON_CONFIG_SOURCE"
    exit 10
  fi
  mkdir -p "$SHANNON_HOME/configs"
  cfg_name="sapphire-$(basename "$SHANNON_CONFIG_SOURCE")"
  cp "$SHANNON_CONFIG_SOURCE" "$SHANNON_HOME/configs/$cfg_name"
  config_arg="CONFIG=./configs/$cfg_name"
fi

if [[ -z "$SHANNON_WORKSPACE" ]]; then
  ts="$(date +%Y%m%d-%H%M%S)"
  SHANNON_WORKSPACE="sapphire-${host//./-}-${ts}"
fi

echo "Shannon target: $TARGET_URL"
echo "Shannon repo:   $scan_repo_dir"
echo "Shannon output: $SHANNON_OUTPUT_DIR"
echo "Workspace:      $SHANNON_WORKSPACE"
[[ -n "$config_arg" ]] && echo "Config:         $config_arg"
echo

pushd "$SHANNON_HOME" >/dev/null
if [[ -n "$config_arg" ]]; then
  ./shannon start "URL=$TARGET_URL" "REPO=$safe_repo_name" "$config_arg" "OUTPUT=$SHANNON_OUTPUT_DIR" "WORKSPACE=$SHANNON_WORKSPACE"
else
  ./shannon start "URL=$TARGET_URL" "REPO=$safe_repo_name" "OUTPUT=$SHANNON_OUTPUT_DIR" "WORKSPACE=$SHANNON_WORKSPACE"
fi
popd >/dev/null

echo
echo "Shannon run started."
echo "Monitor:"
echo "  cd \"$SHANNON_HOME\" && ./shannon logs"
echo "  cd \"$SHANNON_HOME\" && ./shannon workspaces"
