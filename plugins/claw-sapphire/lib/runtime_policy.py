"""Runtime policy enforcement — file-based only.

Controls which agents and tiers can execute tasks.
Adapted from lib/agents/runtime_policy.py — removed Firestore backend.
"""

from __future__ import annotations

import json
from pathlib import Path

POLICY_PATH = Path.home() / ".sapphire" / "runtime_policy.json"

DEFAULT_POLICY = {
    "mode": "open",
    "allowed_tiers": ["t0", "t1", "t2", "t3"],
    "allowed_agents": ["nemotron", "kimi", "claw", "claude"],
    "blocked_repos": [],
    "max_complexity_per_tier": {
        "t0": 2,  # T0 only handles complexity 1-2
        "t1": 3,  # T1 handles up to 3
        "t3": 5,  # T3 handles anything
    },
    "require_verification": True,
    "auto_commit": False,
}


def load() -> dict:
    """Load runtime policy from file."""
    if POLICY_PATH.exists():
        try:
            return {**DEFAULT_POLICY, **json.loads(POLICY_PATH.read_text(encoding="utf-8"))}
        except json.JSONDecodeError:
            pass
    return DEFAULT_POLICY.copy()


def save(policy: dict) -> None:
    """Save runtime policy."""
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    POLICY_PATH.write_text(json.dumps(policy, indent=2))


def is_tier_allowed(tier: str) -> bool:
    """Check if a tier is allowed by policy."""
    return tier in load().get("allowed_tiers", [])


def is_repo_allowed(repo: str) -> bool:
    """Check if a repo can be modified."""
    return repo not in load().get("blocked_repos", [])


def max_complexity(tier: str) -> int:
    """Get max task complexity for a tier."""
    return load().get("max_complexity_per_tier", {}).get(tier, 5)


def should_verify() -> bool:
    """Check if verification is required after fixes."""
    return load().get("require_verification", True)


def can_auto_commit() -> bool:
    """Check if auto-commit is enabled."""
    return load().get("auto_commit", False)
