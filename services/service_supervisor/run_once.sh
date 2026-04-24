#!/bin/zsh
# Rationale: launchd should run this as a one-shot every minute. The Python
# supervisor persists cooldown/rate-limit state, so we avoid adding another
# long-lived process while still getting low-latency self-healing.
set -euo pipefail

cd /Users/aribs/Code/Sapphire
export PYTHONPATH="/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools:${PYTHONPATH:-}"
exec /usr/local/bin/python3 -m service_supervisor "$@"
