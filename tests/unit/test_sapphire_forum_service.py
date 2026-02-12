import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
FORUM_PATH = ROOT_DIR / "services/alpha-engine/src/collaboration/forum.py"


def _load_forum_module():
    spec = importlib.util.spec_from_file_location("sapphire_forum", FORUM_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_create_topic_and_reply_roundtrip(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))

    service = module.SapphireForumService()
    topic = service.create_topic(
        {
            "title": "Quant lane sync",
            "body": "Coordinate ASTER/LIGHTER spread logic updates.",
            "lane": "trading",
            "author": "EMERALD",
            "tags": ["quant", "dex"],
        }
    )

    assert topic["topic_id"].startswith("TOPIC-")
    assert topic["lane"] == "trading"

    reply = service.add_reply(
        topic["topic_id"],
        {
            "body": "Adding validation checks before dispatch.",
            "author": "SAPPHIRE",
            "kind": "proposal",
        },
    )
    assert reply["reply_id"].startswith("REPLY-")

    detail = service.get_topic_detail(topic["topic_id"])
    assert detail is not None
    assert len(detail["replies"]) == 1


def test_topic_sanitizes_sensitive_values(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))

    service = module.SapphireForumService()
    topic = service.create_topic(
        {
            "title": "Secret handling check",
            "body": "token=abcdefg AIzaSyDUMMYKEY1234567890123456789 please redact",
            "lane": "security",
        }
    )

    detail = service.get_topic_detail(topic["topic_id"])
    assert detail is not None
    assert "abcdefg" not in detail["body"]
    assert "AIza" not in detail["body"]


def test_register_scout_rejects_invalid_username(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))

    service = module.SapphireForumService()
    result = asyncio.run(
        service.register_scout_account(
            {
                "username": "invalid name",
                "display_name": "Bad Scout",
                "bio": "should fail",
            }
        )
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_username"


def test_publish_scout_note_stores_locally_without_external_bridge(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.delenv("SAPPHIRE_SCOUT_EXTERNAL_POST_URL", raising=False)

    service = module.SapphireForumService()
    topic = service.create_topic(
        {
            "title": "External research thread",
            "body": "Collect public strategy insights.",
            "lane": "external",
        }
    )

    result = asyncio.run(
        service.publish_scout_note(
            {
                "topic_id": topic["topic_id"],
                "body": "Posting sanitized summary token=abc123",
                "author": "SAPPHIRE_SCOUT",
            }
        )
    )

    assert result["ok"] is True
    assert result["topic_id"] == topic["topic_id"]
    assert result["dispatch"]["dispatched"] is False
    assert "external_url_not_configured" in result["dispatch"]["reason"]
