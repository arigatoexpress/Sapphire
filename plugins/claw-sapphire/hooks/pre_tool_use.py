#!/usr/bin/env python3
"""PreToolUse hook — budget check and policy enforcement.

Called by claw-code BEFORE every tool execution.
Receives tool context via stdin JSON + environment variables.
Exit codes: 0=allow, 2=deny.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from runtime_policy import is_tier_allowed
from token_governor import is_available, remaining

# Map claw-code tool names to risk levels
HIGH_RISK_TOOLS = {"bash", "write_file", "edit_file"}
READ_ONLY_TOOLS = {"read_file", "glob_search", "grep_search", "WebFetch"}


def main():
    """Process PreToolUse hook."""
    # Read context from environment (claw-code hook protocol)
    tool_name = os.environ.get("HOOK_TOOL_NAME", "")
    os.environ.get("HOOK_TOOL_INPUT", "{}")

    # Also try stdin
    if not tool_name:
        try:
            stdin_data = json.loads(sys.stdin.read())
            tool_name = stdin_data.get("tool_name", "")
            json.dumps(stdin_data.get("tool_input", {}))
        except (json.JSONDecodeError, EOFError):
            pass

    if not tool_name:
        # No context — allow (don't break the pipeline)
        sys.exit(0)

    # Read-only tools always allowed
    if tool_name in READ_ONLY_TOOLS:
        sys.exit(0)

    # Sapphire plugin tools always allowed (they have their own checks)
    if tool_name.startswith("sapphire_"):
        sys.exit(0)

    # Check if current tier has budget
    # Determine tier from environment or default
    current_tier = os.environ.get("SAPPHIRE_CURRENT_TIER", "t3")

    if not is_available(current_tier) and current_tier != "t0":
        print(f"⚠️ Budget exhausted for {current_tier}. Remaining: {remaining(current_tier)} tokens.")
        # Don't deny — just warn. The token_governor tracks overages.
        # Deny only if massively over budget
        if current_tier == "t3" and remaining("t3") < -50000:
            print("🛑 Claude budget severely overdrawn. Denying tool execution.")
            sys.exit(2)

    # Policy: check if tool is allowed
    if not is_tier_allowed(current_tier):
        print(f"🛑 Tier {current_tier} is disabled by runtime policy.")
        sys.exit(2)

    # Allow
    sys.exit(0)


if __name__ == "__main__":
    main()
