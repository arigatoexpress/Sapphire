"""Re-export shim — delegates to sapphire_agents.runtime_policy.

For on-prem deployment (no lib/agents install), falls back to local
file-based policy so the service starts without sapphire-agents installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _data_path() -> Path:
    override = str(os.getenv("AGENTIC_RUNTIME_POLICY_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent / "data" / "agent_runtime_policy.json"


def load_runtime_policy() -> dict[str, Any]:
    """Load runtime policy from local JSON file. Returns empty dict if not found."""
    try:
        path = _data_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def allowed_executor_agent_ids(policy: dict[str, Any] | None = None) -> list[str]:
    """Return list of agent IDs permitted to execute tasks."""
    if policy is None:
        policy = load_runtime_policy()
    return list(policy.get("allowed_executor_agent_ids") or [])


def allowed_executor_membership_ids(policy: dict[str, Any] | None = None) -> list[str]:
    """Return list of membership IDs permitted to execute tasks."""
    if policy is None:
        policy = load_runtime_policy()
    return list(policy.get("allowed_executor_membership_ids") or [])
