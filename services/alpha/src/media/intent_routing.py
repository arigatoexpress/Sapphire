"""Helpers for routing natural-language media intents.

Kept small and dependency-free so the chat-intent path can be tested without
booting the full Alpha engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

DEFAULT_TARGETS = ["twitter", "substack"]
TARGET_ALIASES = {
    "x": "twitter",
    "twitter": "twitter",
    "substack": "substack",
    "linkedin": "linkedin",
    "li": "linkedin",
}


def normalize_media_targets(params: dict[str, Any]) -> list[str]:
    raw_targets = params.get("channels") or params.get("targets") or DEFAULT_TARGETS
    if isinstance(raw_targets, str):
        raw_targets = [raw_targets]
    targets = [
        TARGET_ALIASES.get(str(item).strip().lower(), str(item).strip().lower())
        for item in raw_targets
        if str(item).strip()
    ]
    return targets or list(DEFAULT_TARGETS)


def queue_media_publish_from_intent(
    *,
    media_manager: Any,
    draft_resolver: Callable[[dict[str, Any]], dict[str, Any]],
    params: dict[str, Any],
    source: str = "chat_intent",
) -> dict[str, Any]:
    draft = draft_resolver(params)
    targets = normalize_media_targets(params)
    return media_manager.request_publish(
        topic=str(draft.get("topic") or params.get("topic") or "market update"),
        title=str(draft.get("title") or ""),
        body=str(draft.get("body") or ""),
        targets=targets,
        source=source,
    )


def format_media_queue_status(status: dict[str, Any]) -> str:
    mode = str(status.get("mode", "unknown"))
    pending = int(status.get("pending_approvals") or 0)
    queued = int(status.get("queue_depth") or 0)
    if pending or queued:
        return f"Media queue: pending `{pending}` | queued `{queued}`. Mode: `{mode}`."
    return f"Queue is clear — nothing pending. Mode: `{mode}`."


__all__ = [
    "format_media_queue_status",
    "normalize_media_targets",
    "queue_media_publish_from_intent",
]
