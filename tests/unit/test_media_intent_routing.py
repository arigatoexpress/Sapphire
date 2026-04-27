from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
ALPHA_DIR = ROOT_DIR / "services" / "alpha"
if str(ALPHA_DIR) not in sys.path:
    sys.path.insert(0, str(ALPHA_DIR))

from src.media.intent_routing import (
    format_media_queue_status,
    normalize_media_targets,
    queue_media_publish_from_intent,
)


class _FakeMediaManager:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def request_publish(self, **kwargs):
        self.requests.append(kwargs)
        return {"request_id": "media:test:0001", "status": "pending_approval", **kwargs}


def test_queue_media_publish_from_intent_builds_draft_and_required_fields() -> None:
    manager = _FakeMediaManager()

    def resolve_draft(params):
        assert params["topic"] == "ETH tokenization"
        return {
            "topic": params["topic"],
            "title": "Sapphire Weekly Lab Note: ETH tokenization",
            "body": "# Sapphire Weekly Lab Note: ETH tokenization\n\nDry-run research note.",
        }

    request = queue_media_publish_from_intent(
        media_manager=manager,
        draft_resolver=resolve_draft,
        params={"topic": "ETH tokenization", "channels": ["x", "substack"]},
    )

    assert request["request_id"] == "media:test:0001"
    assert manager.requests == [
        {
            "topic": "ETH tokenization",
            "title": "Sapphire Weekly Lab Note: ETH tokenization",
            "body": "# Sapphire Weekly Lab Note: ETH tokenization\n\nDry-run research note.",
            "targets": ["twitter", "substack"],
            "source": "chat_intent",
        }
    ]


def test_normalize_media_targets_handles_strings_empty_and_aliases() -> None:
    assert normalize_media_targets({"channels": "twitter"}) == ["twitter"]
    assert normalize_media_targets({"targets": [" linkedin ", ""]}) == ["linkedin"]
    assert normalize_media_targets({"targets": ["x", "li"]}) == ["twitter", "linkedin"]
    assert normalize_media_targets({"channels": []}) == ["twitter", "substack"]


def test_format_media_queue_status_uses_actual_snapshot_keys() -> None:
    message = format_media_queue_status(
        {"mode": "owner_approval", "pending_approvals": 2, "queue_depth": 1}
    )

    assert "pending `2`" in message
    assert "queued `1`" in message
    assert "owner_approval" in message


def test_format_media_queue_status_clear_queue() -> None:
    message = format_media_queue_status(
        {"mode": "draft_only", "pending_approvals": 0, "queue_depth": 0}
    )

    assert "Queue is clear" in message
    assert "draft_only" in message
