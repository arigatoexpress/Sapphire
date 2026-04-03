import asyncio
import importlib.util
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
FORUM_PATH = ROOT_DIR / "services/alpha/src/collaboration/forum.py"


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
    monkeypatch.delenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", raising=False)

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
    monkeypatch.delenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", raising=False)

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


def test_publish_scout_comment_maps_payload_for_moltbook(monkeypatch, tmp_path):
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
                "body": "Scout comment for an external post",
                "author": "SAPPHIRE_SCOUT",
                "post_id": "post_abc123",
            }
        )
    )

    assert result["ok"] is True
    assert result["dispatch_action"] == "comment"
    assert captured["action"] == "comment"
    assert captured["external_url"] == "https://www.moltbook.com/api/v1/posts/post_abc123/comments"
    assert captured["external_token"] == "moltbook_existing_token"
    outbound = captured["outbound_payload"]
    assert outbound["content"] == "Scout comment for an external post"


def test_publish_scout_note_maps_payload_for_gtm_channel(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv(
        "SAPPHIRE_SCOUT_GTM_OUTBOUND_URL",
        "https://app.clawgtm.com/api/v1/agents/dispatch",
    )
    monkeypatch.setenv("SAPPHIRE_SCOUT_GTM_API_TOKEN", "gtm_token_123")

    service = module.SapphireForumService()
    topic = service.create_topic(
        {
            "title": "GTM thread",
            "body": "Track outbound campaign drafts.",
            "lane": "external",
        }
    )

    captured = {}

    async def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return {"dispatched": True, "reason": "ok", "mode": "scout_sandbox"}

    monkeypatch.setattr(service, "_dispatch_scout_bridge", fake_dispatch)

    result = asyncio.run(
        service.publish_scout_note(
            {
                "topic_id": topic["topic_id"],
                "body": "Outbound angle for product-led growth",
                "author": "SAPPHIRE_SCOUT",
                "channel": "gtm",
                "gtm_payload": {"segment": "founders", "campaign": "alpha_launch"},
            }
        )
    )

    assert result["ok"] is True
    assert result["dispatch_action"] == "gtm_outbound"
    assert captured["action"] == "gtm_outbound"
    assert captured["external_url"] == "https://app.clawgtm.com/api/v1/agents/dispatch"
    assert captured["external_token"] == "gtm_token_123"
    outbound = captured["outbound_payload"]
    assert outbound["message"] == "Outbound angle for product-led growth"
    assert outbound["segment"] == "founders"
    assert outbound["campaign"] == "alpha_launch"


def _fake_client_session_factory(status_code: int, payload: dict):
    class _FakeResponse:
        def __init__(self):
            self.status = status_code

        async def text(self):
            return json.dumps(payload)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeClientSession:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None, headers=None):
            return _FakeResponse()

    return _FakeClientSession


def _fake_client_session_factory_sequence(sequence):
    remaining = list(sequence)

    class _FakeResponse:
        def __init__(self, status_code, payload):
            self.status = status_code
            self._payload = payload

        async def text(self):
            return json.dumps(self._payload)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeClientSession:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None, headers=None):
            if remaining:
                status_code, payload = remaining.pop(0)
            else:
                status_code, payload = (500, {"success": False, "error": "unexpected_empty_sequence"})
            return _FakeResponse(status_code, payload)

    return _FakeClientSession


def test_dispatch_scout_sandbox_routes_gtm_action_to_gtm_endpoint(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_SANDBOX_URL", "https://sandbox.example")
    monkeypatch.setenv("SAPPHIRE_SCOUT_SANDBOX_TOKEN", "sandbox_token")

    captured = {}

    class _FakeResponse:
        status = 200

        async def text(self):
            return json.dumps({"ok": True, "dispatch": {"dispatched": True, "reason": "ok", "status": 200}})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeClientSession:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = dict(json or {})
            captured["headers"] = dict(headers or {})
            return _FakeResponse()

    monkeypatch.setattr(module.aiohttp, "ClientSession", _FakeClientSession)

    service = module.SapphireForumService()
    result = asyncio.run(
        service._dispatch_scout_sandbox(
            action="gtm_outbound",
            outbound_payload={"company_url": "https://example.com"},
            external_url="https://app.clawgtm.com/api/v1/agents/dispatch",
            note="dispatch gtm",
        )
    )

    assert result["dispatched"] is True
    assert captured["url"] == "https://sandbox.example/v1/gtm/outbound"
    assert captured["payload"]["external_url_hint"] == "https://app.clawgtm.com/api/v1/agents/dispatch"
    assert captured["payload"]["outbound_payload"]["company_url"] == "https://example.com"
    assert "action" not in captured["payload"]


def test_dispatch_external_detects_moltbook_rate_limit(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))

    response_payload = {
        "success": False,
        "error": "You can only post once every 2 hours",
        "hint": "Wait 2 hours before posting again.",
        "retry_after_minutes": 120,
        "is_new_agent": True,
        "new_agent_hours_remaining": 24,
    }
    monkeypatch.setattr(
        module.aiohttp,
        "ClientSession",
        _fake_client_session_factory(429, response_payload),
    )

    service = module.SapphireForumService()
    result = asyncio.run(
        service._dispatch_external(
            "https://www.moltbook.com/api/v1/posts",
            {"submolt": "general", "title": "x", "content": "y"},
            token="moltbook_token",
        )
    )

    assert result["dispatched"] is False
    assert result["reason"] == "moltbook_rate_limited"
    assert result["attempt"] == 1
    assert result["metadata"]["retry_after_minutes"] == 120
    assert result["metadata"]["is_new_agent"] is True


def test_dispatch_external_detects_moltbook_comment_rate_limit(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))

    response_payload = {
        "success": False,
        "error": "Slow down! You can comment again in 21 seconds.",
        "retry_after_seconds": 21,
        "is_new_agent": True,
        "new_agent_hours_remaining": 15,
    }
    monkeypatch.setattr(
        module.aiohttp,
        "ClientSession",
        _fake_client_session_factory(429, response_payload),
    )

    service = module.SapphireForumService()
    result = asyncio.run(
        service._dispatch_external(
            "https://www.moltbook.com/api/v1/posts/post-123/comments",
            {"content": "x"},
            token="moltbook_token",
        )
    )

    assert result["dispatched"] is False
    assert result["reason"] == "moltbook_rate_limited"
    assert result["attempt"] == 1
    assert result["metadata"]["retry_after_seconds"] == 21
    assert result["metadata"]["is_new_agent"] is True


def test_dispatch_external_marks_pending_verification(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_AUTO_VERIFY_ENABLED", "false")
    monkeypatch.setattr(
        module.aiohttp,
        "ClientSession",
        _fake_client_session_factory(
            201,
            {
                "success": True,
                "verification_required": True,
                "verification": {"code": "abc123", "challenge": "challenge"},
                "post": {"id": "post-123", "url": "/post/post-123", "verification_status": "pending"},
            },
        ),
    )

    service = module.SapphireForumService()
    result = asyncio.run(
        service._dispatch_external(
            "https://www.moltbook.com/api/v1/posts",
            {"submolt": "general", "title": "x", "content": "y"},
            token="moltbook_token",
        )
    )

    assert result["dispatched"] is True
    assert result["reason"] == "ok_pending_verification"
    assert result["metadata"]["verification_required"] is True
    assert result["metadata"]["post_id"] == "post-123"
    assert result["metadata"]["post_verification_status"] == "pending"


def test_dispatch_external_auto_verifies_moltbook_challenge(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_AUTO_VERIFY_ENABLED", "true")
    monkeypatch.setattr(
        module.aiohttp,
        "ClientSession",
        _fake_client_session_factory_sequence(
            [
                (
                    201,
                    {
                        "success": True,
                        "verification_required": True,
                        "verification": {"code": "abc123", "challenge": "what is sixteen plus twenty two?"},
                        "post": {
                            "id": "post-123",
                            "url": "/post/post-123",
                            "verification_status": "pending",
                        },
                    },
                ),
                (200, {"success": True, "verified": True}),
            ]
        ),
    )

    service = module.SapphireForumService()
    result = asyncio.run(
        service._dispatch_external(
            "https://www.moltbook.com/api/v1/posts",
            {"submolt": "general", "title": "x", "content": "y"},
            token="moltbook_token",
        )
    )

    assert result["dispatched"] is True
    assert result["reason"] == "ok_verified"
    assert result["metadata"]["verification_attempted"] is True
    assert result["metadata"]["verification_status"] == "verified"
    assert result["metadata"]["verification_answer"] == "38.00"


def test_solve_moltbook_challenge_supports_number_words(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    service = module.SapphireForumService()

    answer = service._solve_moltbook_challenge("Please solve: thirty eight minus ten")
    assert answer == "28.00"


def test_dispatch_bridge_skips_fallback_on_provider_constraints(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    service = module.SapphireForumService()

    async def fake_external(url, payload, token=""):
        return {"dispatched": False, "reason": "moltbook_rate_limited"}

    async def fake_fallback(action, payload, note):
        raise AssertionError("Fallback should not run for provider constraints")

    monkeypatch.setattr(service, "_dispatch_external", fake_external)
    monkeypatch.setattr(service, "_dispatch_openclaw_fallback", fake_fallback)

    result = asyncio.run(
        service._dispatch_scout_bridge(
            action="publish",
            outbound_payload={"x": "y"},
            external_url="https://www.moltbook.com/api/v1/posts",
            external_token="moltbook_token",
            note="test",
        )
    )

    assert result["dispatched"] is False
    assert result["reason"] == "moltbook_rate_limited"
    assert result["mode"] == "external_http"


def test_register_scout_treats_already_registered_as_success(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL", "https://www.moltbook.com/api/v1/agents/register")
    service = module.SapphireForumService()

    async def fake_dispatch(**kwargs):
        return {
            "dispatched": False,
            "reason": "moltbook_already_registered",
            "mode": "external_http",
            "metadata": {},
        }

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
    assert result["dispatch"]["dispatched"] is True
    assert result["dispatch"]["reason"] == "moltbook_already_registered"
    assert result["dispatch"]["metadata"]["already_registered"] is True


def test_register_scout_uses_existing_moltbook_token_without_dispatch(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL", "https://www.moltbook.com/api/v1/agents/register")
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "moltbook_existing_token")
    service = module.SapphireForumService()

    async def fake_dispatch(**kwargs):
        raise AssertionError("Dispatch should be skipped when a Moltbook token already exists")

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
    assert result["dispatch"]["dispatched"] is True
    assert result["dispatch"]["reason"] == "moltbook_token_present"
    assert result["dispatch"]["metadata"]["already_registered"] is True


def test_scout_status_assumes_registered_when_moltbook_token_present(monkeypatch, tmp_path):
    module = _load_forum_module()
    monkeypatch.setenv("SAPPHIRE_FORUM_STORE_PATH", str(tmp_path / "forum.json"))
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL", "https://www.moltbook.com/api/v1/agents/register")
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_POST_URL", "https://www.moltbook.com/api/v1/posts")
    monkeypatch.setenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "moltbook_existing_token")
    monkeypatch.setenv("SAPPHIRE_SCOUT_USERNAME", "sapphire_scout")
    monkeypatch.setenv("SAPPHIRE_SCOUT_DISPLAY_NAME", "Sapphire Scout")

    service = module.SapphireForumService()
    status = service.scout_status()

    assert status["registration"]["registered"] is True
    assert status["registration"]["registered_runtime"] is False
    assert status["registration"]["assumed_registered"] is True
    assert status["registration"]["registered_source"] == "api_token"
    assert status["registration"]["username"] == "sapphire_scout"
    assert status["external_bridge"]["provider"] == "moltbook"
    assert status["external_bridge"]["external_ready"] is True
    assert status["external_bridge"]["provider_state"] == "registered_active"
