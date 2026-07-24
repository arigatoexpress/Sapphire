#!/usr/bin/env python3
"""sapphire_state — persistent factory memory.

Tracks issues across runs so the factory doesn't re-attempt failed fixes.
Implements backoff: after N failed attempts, skip for increasing periods.

Input schema:
    {"action": "get"} — return full state
    {"action": "get_issue", "issue_id": "sha256..."} — get one issue
    {"action": "record_issue", "repo": "Sapphire", "type": "lint_error", "file": "main.py", "description": "..."} — record new issue
    {"action": "record_attempt", "issue_id": "...", "tier": "t1", "result": "fixed"|"failed", "reason": "..."} — record fix attempt
    {"action": "should_skip", "issue_id": "..."} — check if issue is in backoff
    {"action": "metrics"} — daily metrics summary
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

STATE_PATH = Path.home() / ".sapphire" / "factory_state.json"

# Backoff: after N failures, wait N*2 hours before retrying
MAX_ATTEMPTS_BEFORE_BACKOFF = 2
BACKOFF_HOURS_PER_ATTEMPT = 2


def _load() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"issues": {}, "metrics": {}}


def _save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _issue_id(repo: str, issue_type: str, file: str, description: str) -> str:
    """Generate deterministic issue ID."""
    content = f"{repo}:{issue_type}:{file}:{description[:200]}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def record_issue(repo: str, issue_type: str, file: str, description: str) -> dict:
    """Record a new issue (or return existing if already tracked)."""
    state = _load()
    iid = _issue_id(repo, issue_type, file, description)

    if iid not in state["issues"]:
        state["issues"][iid] = {
            "repo": repo,
            "type": issue_type,
            "file": file,
            "description": description[:500],
            "first_seen": datetime.now(UTC).isoformat(),
            "status": "open",
            "attempts": [],
            "backoff_until": None,
        }
        _save(state)

    return {"issue_id": iid, **state["issues"][iid]}


def record_attempt(issue_id: str, tier: str, result: str, reason: str = "") -> dict:
    """Record a fix attempt for an issue."""
    state = _load()

    if issue_id not in state["issues"]:
        return {"error": f"Issue {issue_id} not found"}

    issue = state["issues"][issue_id]
    issue["attempts"].append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "tier": tier,
            "result": result,
            "reason": reason[:200],
        }
    )

    if result == "fixed":
        issue["status"] = "fixed"
        issue["backoff_until"] = None
    elif result == "failed":
        failed_count = sum(1 for a in issue["attempts"] if a["result"] == "failed")
        if failed_count >= MAX_ATTEMPTS_BEFORE_BACKOFF:
            hours = failed_count * BACKOFF_HOURS_PER_ATTEMPT
            backoff = datetime.now(UTC) + timedelta(hours=hours)
            issue["backoff_until"] = backoff.isoformat()

    # Track daily metrics
    today = _today()
    if today not in state["metrics"]:
        state["metrics"][today] = {"scanned": 0, "fixed": 0, "failed": 0, "skipped": 0}
    state["metrics"][today][result if result in ("fixed", "failed") else "scanned"] += 1

    _save(state)
    return {"issue_id": issue_id, **issue}


def should_skip(issue_id: str) -> dict:
    """Check if an issue is in backoff (shouldn't be retried yet)."""
    state = _load()
    issue = state["issues"].get(issue_id)

    if not issue:
        return {"skip": False, "reason": "issue not found"}

    if issue["status"] == "fixed":
        return {"skip": True, "reason": "already fixed"}

    if issue.get("backoff_until"):
        backoff = datetime.fromisoformat(issue["backoff_until"])
        if datetime.now(UTC) < backoff:
            return {
                "skip": True,
                "reason": f"in backoff until {issue['backoff_until']}",
                "attempts": len(issue["attempts"]),
            }

    return {"skip": False, "reason": "ready for retry", "attempts": len(issue["attempts"])}


def get_metrics() -> dict:
    """Get daily metrics summary."""
    state = _load()
    today = _today()
    today_metrics = state["metrics"].get(
        today, {"scanned": 0, "fixed": 0, "failed": 0, "skipped": 0}
    )

    total_issues = len(state["issues"])
    open_issues = sum(1 for i in state["issues"].values() if i["status"] == "open")
    fixed_issues = sum(1 for i in state["issues"].values() if i["status"] == "fixed")
    in_backoff = sum(
        1
        for i in state["issues"].values()
        if i.get("backoff_until") and datetime.fromisoformat(i["backoff_until"]) > datetime.now(UTC)
    )

    return {
        "today": today_metrics,
        "total_issues": total_issues,
        "open": open_issues,
        "fixed": fixed_issues,
        "in_backoff": in_backoff,
    }


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        input_data = {"action": "metrics"}

    action = input_data.get("action", "metrics")

    if action == "get":
        print(json.dumps(_load(), indent=2))
    elif action == "record_issue":
        result = record_issue(
            input_data["repo"],
            input_data["type"],
            input_data.get("file", ""),
            input_data.get("description", ""),
        )
        print(json.dumps(result, indent=2))
    elif action == "record_attempt":
        result = record_attempt(
            input_data["issue_id"],
            input_data["tier"],
            input_data["result"],
            input_data.get("reason", ""),
        )
        print(json.dumps(result, indent=2))
    elif action == "should_skip":
        result = should_skip(input_data["issue_id"])
        print(json.dumps(result, indent=2))
    elif action == "metrics":
        print(json.dumps(get_metrics(), indent=2))
    else:
        print(json.dumps({"error": f"Unknown action: {action}"}))


if __name__ == "__main__":
    main()
