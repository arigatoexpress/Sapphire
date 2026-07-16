#!/usr/bin/env bash
# Ralph Loop — iterative autonomous improvement for the Sapphire stack.
#
# Usage:
#   ./ralph-loop.sh <task-file.md> [--max-iterations N] [--completion-promise "DONE"]
#
# The script repeatedly invokes a Kimi Code CLI subagent with the task file,
# checks the output for the completion promise, and loops until the promise
# appears or max iterations is reached.
#
# Safety:
#   - Read-only / reversible work only.
#   - No live trading, no outward deploys, no money movement.
#   - Each iteration commits to a feature branch; never force-pushes main.

set -euo pipefail

TASK_FILE="${1:-}"
MAX_ITERATIONS="${MAX_ITERATIONS:-20}"
COMPLETION_PROMISE="${COMPLETION_PROMISE:-DONE}"

if [[ -z "$TASK_FILE" ]]; then
  echo "Usage: $0 <task-file.md> [--max-iterations N] [--completion-promise \"DONE\"]" >&2
  exit 1
fi

if [[ ! -f "$TASK_FILE" ]]; then
  echo "Task file not found: $TASK_FILE" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$REPO_ROOT/data/logs/ralph-loop"
mkdir -p "$LOG_DIR"

for i in $(seq 1 "$MAX_ITERATIONS"); do
  ITER_LOG="$LOG_DIR/iter-$(date +%s).log"
  echo "=== Ralph iteration $i / $MAX_ITERATIONS ===" | tee -a "$ITER_LOG"

  # Invoke a background coder agent with the task file.
  # This requires the Kimi Code CLI to be available in PATH as `kimi`.
  if command -v kimi >/dev/null 2>&1; then
    kimi agent run --type coder --prompt "$(cat "$TASK_FILE")" >> "$ITER_LOG" 2>&1
  else
    echo "kimi CLI not found; falling back to local subagent invocation is not supported." >&2
    exit 3
  fi

  if grep -q "$COMPLETION_PROMISE" "$ITER_LOG"; then
    echo "Completion promise '$COMPLETION_PROMISE' found. Ralph loop finished at iteration $i." | tee -a "$ITER_LOG"
    exit 0
  fi

  echo "Iteration $i did not complete. Sleeping 10s before next loop..." | tee -a "$ITER_LOG"
  sleep 10
done

echo "Max iterations ($MAX_ITERATIONS) reached without completion promise." >&2
exit 4
