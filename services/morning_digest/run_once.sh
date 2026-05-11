#!/bin/zsh
# Rationale: a one-shot launchd calendar job is enough for the 8 AM digest.
# dev_pulse does the fan-out and notify.py writes PM-bot-reviewed drafts.
set -euo pipefail

SCRIPT_PATH="${0:A}"
SCRIPT_DIR="${SCRIPT_PATH:h}"
REPO_ROOT="${SCRIPT_DIR:h:h}"

cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/plugins/claw-sapphire/tools:${PYTHONPATH:-}"
exec /usr/local/bin/python3 -m morning_digest "$@"
