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


def test_topic_sanitizes_moltbook_api_key(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))

    service = module.SapphireForumService()
    topic = service.create_topic(
        {
            "title": "Moltbook key handling check",
            "body": "api_key=moltbook_abc123456789SECRETVALUE",
            "lane": "security",
        }
    )
    detail = service.get_topic_detail(topic["topic_id"])
    assert detail is not None
    assert "moltbook_" not in detail["body"]
    assert "[REDACTED" in detail["body"]


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


def test_register_scout_maps_payload_for_moltbook(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL", "https://www.moltbook.com/api/v1/agents/register")
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "moltbook_existing_token")

    service = module.SapphireForumService()
    captured = {}

    async def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return {"dispatched": True, "reason": "ok", "mode": "external_http"}

    monkeypatch.setattr(service, "_dispatch_scout_bridge", fake_dispatch)

    result = asyncio.run(
        service.register_scout_account(
            {
                "username": "sapphire_scout",
                "display_name": "Sapphire Scout",
                "bio": "Least privilege scout",
            }
        )
    )

    assert result["ok"] is True
    assert captured["action"] == "register"
    assert captured["external_url"] == "https://www.moltbook.com/api/v1/agents/register"
    # Moltbook register endpoint does not use bearer token.
    assert captured["external_token"] == ""
    outbound = captured["outbound_payload"]
    assert outbound["name"] == "Sapphire Scout"
    assert "description" in outbound
    assert "username" not in outbound


def test_register_scout_maps_payload_for_moltbook_root_domain(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL", "https://moltbook.com/api/v1/agents/register")
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "moltbook_existing_token")

    service = module.SapphireForumService()
    captured = {}

    async def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return {"dispatched": True, "reason": "ok", "mode": "external_http"}

    monkeypatch.setattr(service, "_dispatch_scout_bridge", fake_dispatch)

    result = asyncio.run(
        service.register_scout_account(
            {
                "username": "sapphire_scout",
                "display_name": "Sapphire Scout",
                "bio": "Least privilege scout",
            }
        )
    )

    assert result["ok"] is True
    assert captured["external_url"] == "https://moltbook.com/api/v1/agents/register"
    assert captured["external_token"] == ""
    outbound = captured["outbound_payload"]
    assert outbound["name"] == "Sapphire Scout"
    assert "username" not in outbound


def test_publish_scout_maps_payload_for_moltbook(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_POST_URL", "https://www.moltbook.com/api/v1/posts")
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "moltbook_existing_token")

    service = module.SapphireForumService()
    topic = service.create_topic(
        {
            "title": "External thread",
            "body": "Track scout updates.",
            "lane": "external",
        }
    )

    captured = {}

    async def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return {"dispatched": True, "reason": "ok", "mode": "external_http"}

    monkeypatch.setattr(service, "_dispatch_scout_bridge", fake_dispatch)

    result = asyncio.run(
        service.publish_scout_note(
            {
                "topic_id": topic["topic_id"],
                "body": "Scout note for Moltbook publishing",
                "author": "SAPPHIRE_SCOUT",
                "submolt": "general",
            }
        )
    )

    assert result["ok"] is True
    assert captured["action"] == "publish"
    assert captured["external_url"] == "https://www.moltbook.com/api/v1/posts"
    assert captured["external_token"] == "moltbook_existing_token"
    outbound = captured["outbound_payload"]
    assert outbound["submolt"] == "general"
    assert outbound["content"] == "Scout note for Moltbook publishing"
    assert "title" in outbound
