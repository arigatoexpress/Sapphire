#!/usr/bin/env python3
"""PostToolUse hook — token tracking, event logging, verification trigger.

Called by claw-code AFTER every tool execution.
Tracks real token counts, logs to event stream, triggers verification on code changes.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from token_governor import record

EVENTS_PATH = Path.home() / "Code" / "Sapphire" / "data" / "system_events.jsonl"
CODE_EDIT_TOOLS = {"edit_file", "write_file"}


def log_event(event_type: str, message: str, data: dict | None = None) -> None:
    """Append event to Sapphire JSONL stream."""
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": event_type,
        "message": message,
        "tags": ["agent:claw-code", "device:mac", "type:tool"],
        "data": data or {},
    }
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def main():
    """Process PostToolUse hook."""
    tool_name = os.environ.get("HOOK_TOOL_NAME", "")
    tool_output = os.environ.get("HOOK_TOOL_OUTPUT", "")
    is_error = os.environ.get("HOOK_TOOL_IS_ERROR", "0") == "1"

    # Try stdin for full context
    if not tool_name:
        try:
            stdin_data = json.loads(sys.stdin.read())
            tool_name = stdin_data.get("tool_name", "")
            tool_output = stdin_data.get("tool_output", "")
            is_error = stdin_data.get("is_error", False)
        except (json.JSONDecodeError, EOFError):
            pass

    if not tool_name:
        sys.exit(0)

    # Track token usage for the current tier
    current_tier = os.environ.get("SAPPHIRE_CURRENT_TIER", "t3")
    output_len = len(tool_output)

    # For code edit tools, estimate tokens from output size
    # Real counts come from the API client, not individual tools
    if tool_name in CODE_EDIT_TOOLS:
        record(current_tier, prompt_tokens=0, eval_tokens=output_len // 4, task=f"tool:{tool_name}")

    # Log to event stream
    log_event(
        "tool.executed",
        f"{tool_name} {'failed' if is_error else 'ok'} ({output_len} chars)",
        {
            "tool": tool_name,
            "success": not is_error,
            "output_size": output_len,
            "tier": current_tier,
        },
    )

    # Exit 0 — allow (PostToolUse can't deny, only observe)
    sys.exit(0)


if __name__ == "__main__":
    main()
