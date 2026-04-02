"""Sapphire event stream tool for claw-code.

Read/write JSONL events for the Sapphire OS event system.
Events are tagged with namespaces: project:, agent:, priority:, type:, service:, device:
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_EVENTS_PATH = Path.home() / "Code" / "Sapphire" / "data" / "system_events.jsonl"


def get_events_path() -> Path:
    """Resolve the events JSONL file path."""
    env_path = os.environ.get("SAPPHIRE_EVENTS_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_EVENTS_PATH


def publish_event(
    event_type: str,
    message: str,
    tags: list[str] | None = None,
    data: dict | None = None,
) -> dict:
    """Publish an event to the Sapphire event stream.

    Args:
        event_type: Event type (e.g., task.created, deploy.started, tool.executed)
        message: Human-readable description.
        tags: List of tags (e.g., ["agent:claude", "priority:p1", "device:mac"])
        data: Optional structured data payload.

    Returns:
        The published event dict.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "message": message,
        "tags": tags or [],
        "data": data or {},
    }

    path = get_events_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "a") as f:
        f.write(json.dumps(event) + "\n")

    return event


def read_events(
    limit: int = 50,
    tag_filter: str | None = None,
    type_filter: str | None = None,
    since: str | None = None,
) -> list[dict]:
    """Read events from the stream with optional filtering.

    Args:
        limit: Max events to return (most recent first).
        tag_filter: Only events containing this tag.
        type_filter: Only events matching this type prefix.
        since: ISO timestamp — only events after this time.
    """
    path = get_events_path()
    if not path.exists():
        return []

    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if tag_filter and tag_filter not in event.get("tags", []):
                continue
            if type_filter and not event.get("type", "").startswith(type_filter):
                continue
            if since and event.get("timestamp", "") < since:
                continue

            events.append(event)

    # Return most recent first, up to limit
    return events[-limit:][::-1]


def run(action: str = "read", **kwargs) -> str:
    """Tool entry point for claw-code."""
    if action == "publish":
        event = publish_event(
            event_type=kwargs.get("event_type", "generic"),
            message=kwargs.get("message", ""),
            tags=kwargs.get("tags", []),
            data=kwargs.get("data", {}),
        )
        return json.dumps(event, indent=2)
    else:
        events = read_events(
            limit=kwargs.get("limit", 50),
            tag_filter=kwargs.get("tag_filter"),
            type_filter=kwargs.get("type_filter"),
            since=kwargs.get("since"),
        )
        return json.dumps(events, indent=2)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        print(run("publish", event_type="test", message="Test event from CLI", tags=["agent:claude", "device:mac"]))
    else:
        print(run("read", limit=10))
