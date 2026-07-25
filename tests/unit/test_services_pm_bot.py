"""Tests for services/pm_bot/server.py — Telegram-facing PM bot wrapper.

The service has an in-tree test file at ``services/pm_bot/test_server_token.py``
that pytest does NOT discover by default (``testpaths = ["tests"]``). Those
existing tests focus on token resolution, webhook secret resolution, and
webhook authentication. This file lives under ``tests/unit/`` so the unit
suite picks it up, and it covers the gaps:

    * ``_message_payload`` — extract the message dict from the update envelope
    * ``_chat_id`` — chat-id extraction across the various Telegram shapes
    * ``process_update`` — full update -> handler -> sendMessage round trip
    * ``TelegramAPI._post`` error mapping (HTTP error, ok=False)
    * ``TelegramAPI.send_message`` payload construction
    * ``TelegramAPI.get_updates`` result coercion (non-list, mixed types)
    * ``TelegramAPI.delete_webhook`` flag wiring
    * ``_validate_startup_config`` token-required + mode-required guards
    * ``health`` endpoint full shape (mode, polling_active, last_poll_error)
    * Webhook handler end-to-end with no secret configured
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PM_BOT_DIR = REPO_ROOT / "services" / "pm_bot"
TOOL_DIR = REPO_ROOT / "plugins" / "claw-sapphire" / "tools"

# Ensure the pm_bot service dir is on sys.path so ``import server`` resolves.
if str(PM_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(PM_BOT_DIR))


@pytest.fixture
def reload_server(monkeypatch):
    """Reload services/pm_bot/server.py with a fresh env so module-level
    SETTINGS rebuilds. Returns a callable that performs the reload.
    """
    monkeypatch.delenv("SAPPHIRE_PM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_PROBE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_AGENTIC_DRY_RUN", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_AGENT_CHAT_IDS", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_AGENT_THREAD_IDS", raising=False)
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token-default")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "0")

    sys.modules.pop("server", None)

    def _load():
        return importlib.import_module("server")

    return _load


# ---------------------------------------------------------------------------
# _message_payload / _chat_id
# ---------------------------------------------------------------------------


def test_message_payload_extracts_message_dict(reload_server):
    server = reload_server()
    update = {"update_id": 1, "message": {"chat": {"id": 99}, "text": "hi"}}
    assert server._message_payload(update) == {"chat": {"id": 99}, "text": "hi"}


def test_message_payload_extracts_edited_message_dict(reload_server):
    server = reload_server()
    update = {"update_id": 2, "edited_message": {"chat": {"id": 99}, "text": "hi again"}}
    assert server._message_payload(update) == {"chat": {"id": 99}, "text": "hi again"}


def test_message_payload_falls_back_to_top_level_when_missing(reload_server):
    """If the update has no ``message`` key, the top-level dict is treated as the
    message — matches the upstream tolerance pattern.
    """
    server = reload_server()
    bare = {"chat": {"id": 5}, "text": "hello"}
    assert server._message_payload(bare) == bare


def test_chat_id_from_chat_object(reload_server):
    server = reload_server()
    assert server._chat_id({"message": {"chat": {"id": 12345}}}) == 12345


def test_chat_id_from_top_level_chat_id(reload_server):
    """Some legacy or simulated updates pass chat_id at the message root."""
    server = reload_server()
    assert server._chat_id({"message": {"chat_id": 67}}) == 67


def test_chat_id_returns_none_for_unparseable(reload_server):
    server = reload_server()
    assert server._chat_id({"message": {"chat": {"id": "not-a-number"}}}) is None
    assert server._chat_id({"message": {}}) is None
    assert server._chat_id({}) is None


def test_chat_id_coerces_numeric_strings(reload_server):
    """Telegram sometimes serializes chat ids as strings; int() should rescue them."""
    server = reload_server()
    assert server._chat_id({"message": {"chat": {"id": "42"}}}) == 42
    assert server._chat_id({"message": {"chat_id": "100"}}) == 100


# ---------------------------------------------------------------------------
# process_update
# ---------------------------------------------------------------------------


def test_process_update_dispatches_to_handler_and_sends_message(reload_server, monkeypatch):
    server = reload_server()

    if str(TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(TOOL_DIR))
    import sapphire_pm_bot

    monkeypatch.setattr(
        sapphire_pm_bot,
        "handle_telegram_command",
        lambda upd: {"text": "PONG", "parse_mode": "Markdown"},
    )

    sent: list[dict] = []

    def fake_send_message(**kwargs):
        sent.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fake_send_message)

    update = {"update_id": 9, "message": {"chat": {"id": 77}, "text": "/help"}}
    assert server.process_update(update) is True
    assert sent == [
        {
            "chat_id": 77,
            "text": "PONG",
            "parse_mode": "Markdown",
            "reply_markup": None,
            "disable_notification": False,
            "reply_parameters": None,
            "message_thread_id": None,
            "direct_messages_topic_id": None,
        }
    ]


def test_process_update_replies_in_thread_with_defaults(reload_server, monkeypatch):
    server = reload_server()

    if str(TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(TOOL_DIR))
    import sapphire_pm_bot

    monkeypatch.setattr(
        sapphire_pm_bot,
        "handle_telegram_command",
        lambda upd: {"text": "PONG", "parse_mode": "Markdown"},
    )

    sent: list[dict[str, Any]] = []

    def fake_send_message(**kwargs):
        sent.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fake_send_message)

    update = {
        "update_id": 10,
        "edited_message": {
            "message_id": 55,
            "message_thread_id": 9001,
            "direct_messages_topic_id": 7,
            "chat": {"id": 77},
            "text": "/help",
        },
    }
    assert server.process_update(update) is True
    assert sent == [
        {
            "chat_id": 77,
            "text": "PONG",
            "parse_mode": "Markdown",
            "reply_markup": None,
            "disable_notification": False,
            "reply_parameters": {"message_id": 55},
            "message_thread_id": 9001,
            "direct_messages_topic_id": 7,
        }
    ]


def test_process_update_dispatches_command_inside_agent_chat_scope(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_AGENT_CHAT_IDS", "-1001")
    server = reload_server()

    if str(TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(TOOL_DIR))
    import sapphire_pm_bot

    monkeypatch.setattr(
        sapphire_pm_bot,
        "handle_telegram_command",
        lambda upd: {"text": "PONG", "parse_mode": "Markdown"},
    )

    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    update = {"update_id": 101, "message": {"chat": {"id": -1001}, "text": "/help"}}
    assert server.process_update(update) is True
    assert sent[0]["chat_id"] == -1001
    assert sent[0]["text"] == "PONG"


def test_process_update_rejects_command_outside_agent_chat_scope(
    reload_server, monkeypatch, tmp_path
):
    draft_queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_AGENT_CHAT_IDS", "-1001")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "1")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(draft_queue_path))
    server = reload_server()

    if str(TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(TOOL_DIR))
    import sapphire_pm_bot

    monkeypatch.setattr(
        sapphire_pm_bot,
        "handle_telegram_command",
        lambda _upd: pytest.fail("out-of-scope command must not dispatch"),
    )

    def fail_send(**_kwargs):
        raise AssertionError("out-of-scope command must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {"update_id": 102, "message": {"chat": {"id": -2002}, "text": "/help"}}
    assert server.process_update(update) is True

    from lib.telegram.draft_queue import read_drafts

    drafts = read_drafts(draft_queue_path)
    assert len(drafts) == 1
    assert drafts[0].kind == "rejected_update"
    assert drafts[0].topic == "ops"
    assert drafts[0].status == "pending_confirmation"
    assert drafts[0].metadata["action"] == "chat_not_allowed"
    assert "No PM-bot command was dispatched" in drafts[0].body


def test_process_update_rejects_command_outside_agent_thread_scope(
    reload_server, monkeypatch, tmp_path
):
    draft_queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_AGENT_CHAT_IDS", "-1001")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_AGENT_THREAD_IDS", "7")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "1")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(draft_queue_path))
    server = reload_server()

    monkeypatch.setattr(
        server.TELEGRAM_API,
        "send_message",
        lambda **_kw: pytest.fail("out-of-scope topic must not send"),
    )

    update = {
        "update_id": 103,
        "message": {"chat": {"id": -1001}, "message_thread_id": 9, "text": "/help"},
    }
    assert server.process_update(update) is True

    from lib.telegram.draft_queue import read_drafts

    drafts = read_drafts(draft_queue_path)
    assert len(drafts) == 1
    assert drafts[0].metadata["action"] == "topic_not_allowed"
    assert drafts[0].metadata["message_thread_id"] == 9


def test_process_update_returns_false_when_no_text(reload_server, monkeypatch):
    server = reload_server()
    sent: list[dict] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    # No "text" field — must short-circuit before invoking the handler.
    assert server.process_update({"message": {"chat": {"id": 1}}}) is False
    assert sent == []


def test_process_update_returns_false_when_chat_id_missing(reload_server, monkeypatch):
    server = reload_server()
    sent: list[dict] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    assert server.process_update({"message": {"text": "hi"}}) is False
    assert sent == []


def test_process_update_returns_false_when_handler_returns_empty_text(reload_server, monkeypatch):
    server = reload_server()
    if str(TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(TOOL_DIR))
    import sapphire_pm_bot

    monkeypatch.setattr(sapphire_pm_bot, "handle_telegram_command", lambda upd: {"text": "   "})
    sent: list[dict] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    update = {"message": {"chat": {"id": 8}, "text": "/noop"}}
    assert server.process_update(update) is False
    assert sent == []


def test_process_update_ignores_duplicate_update_ids(reload_server, monkeypatch):
    server = reload_server()
    if str(TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(TOOL_DIR))
    import sapphire_pm_bot

    monkeypatch.setattr(
        sapphire_pm_bot,
        "handle_telegram_command",
        lambda upd: {"text": "first", "parse_mode": None},
    )
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    update = {"update_id": 444, "message": {"message_id": 9, "chat": {"id": 8}, "text": "/help"}}
    assert server.process_update(update) is True
    assert server.process_update(update) is False
    assert len(sent) == 1


def test_process_update_returns_false_for_non_dict_payload(reload_server, monkeypatch):
    server = reload_server()
    sent: list[dict] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    # message is not a dict — process_update should bail
    assert server.process_update({"update_id": 1, "message": "not-a-dict"}) is False
    assert sent == []


def test_process_update_accepts_callback_query_dry_run_without_sending(reload_server, monkeypatch):
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("callback dry-run must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 501,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 123},
            "data": "draft:approve:abc123",
            "message": {"message_id": 77, "chat": {"id": -1001}},
        },
    }

    assert server.process_update(update) is True


def test_process_update_queues_callback_dry_run_draft(reload_server, monkeypatch, tmp_path):
    draft_queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "1")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(draft_queue_path))
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("callback dry-run must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 601,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 123, "username": "ari"},
            "data": "draft:approve:abc123",
            "message": {"message_id": 77, "chat": {"id": -1001}},
        },
    }

    assert server.process_update(update) is True
    from lib.telegram.draft_queue import read_drafts

    drafts = read_drafts(draft_queue_path)
    assert len(drafts) == 1
    assert drafts[0].kind == "draft_callback"
    assert drafts[0].status == "pending_confirmation"
    assert drafts[0].target_chat_id == -1001
    assert drafts[0].metadata["action"] == "approve"
    assert drafts[0].metadata["draft_id"] == "abc123"


def test_process_update_accepts_message_reaction_dry_run_without_sending(
    reload_server, monkeypatch
):
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("reaction dry-run must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 502,
        "message_reaction": {
            "chat": {"id": -1001},
            "message_id": 88,
            "date": 1_779_000_000,
            "old_reaction": [],
            "new_reaction": [{"type": "emoji", "emoji": "👍"}],
            "user": {"id": 123},
        },
    }

    assert server.process_update(update) is True


def test_process_update_queues_reaction_feedback_draft(reload_server, monkeypatch, tmp_path):
    draft_queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "1")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(draft_queue_path))
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("reaction dry-run must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 602,
        "message_reaction": {
            "chat": {"id": -1001},
            "message_id": 88,
            "date": 1_779_000_000,
            "old_reaction": [],
            "new_reaction": [{"type": "emoji", "emoji": "👍"}],
            "user": {"id": 123},
        },
    }

    assert server.process_update(update) is True
    from lib.telegram.draft_queue import read_drafts

    drafts = read_drafts(draft_queue_path)
    assert len(drafts) == 1
    assert drafts[0].kind == "feedback_signal"
    assert drafts[0].requires_confirmation is False
    assert drafts[0].metadata["route"] == "feedback"
    assert drafts[0].metadata["external_side_effect"] is False


def test_process_update_accepts_message_reaction_count_dry_run_without_sending(
    reload_server, monkeypatch
):
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("reaction-count dry-run must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 503,
        "message_reaction_count": {
            "chat": {"id": -1001},
            "message_id": 89,
            "date": 1_779_000_000,
            "reactions": [{"type": {"type": "emoji", "emoji": "🔥"}, "total_count": 3}],
        },
    }

    assert server.process_update(update) is True


def test_process_update_blocks_high_risk_callback_without_sending(reload_server, monkeypatch):
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("blocked callback must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 504,
        "callback_query": {
            "id": "callback-2",
            "from": {"id": 123},
            "data": "trade:BTC:long",
            "message": {"message_id": 77, "chat": {"id": -1001}},
        },
    }

    assert server.process_update(update) is True


def test_process_update_queues_blocked_callback_for_manual_review(
    reload_server, monkeypatch, tmp_path
):
    draft_queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "1")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(draft_queue_path))
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("blocked callback must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 603,
        "callback_query": {
            "id": "callback-2",
            "from": {"id": 123},
            "data": "trade:BTC:long",
            "message": {"message_id": 77, "chat": {"id": -1001}},
        },
    }

    assert server.process_update(update) is True
    from lib.telegram.draft_queue import read_drafts

    drafts = read_drafts(draft_queue_path)
    assert len(drafts) == 1
    assert drafts[0].kind == "blocked_update"
    assert drafts[0].status == "pending_confirmation"
    assert "No external action" in drafts[0].body


def test_process_update_accepts_guest_message_as_no_send_draft_route(reload_server, monkeypatch):
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("guest message draft route must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 505,
        "guest_message": {
            "chat": {"id": -1001},
            "guest_query_id": "guest-1",
            "text": "what changed?",
        },
    }

    assert server.process_update(update) is True


def test_process_update_queues_guest_message_reply_draft(reload_server, monkeypatch, tmp_path):
    draft_queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "1")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(draft_queue_path))
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("guest message draft route must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 604,
        "guest_message": {
            "chat": {"id": -1001},
            "guest_query_id": "guest-1",
            "text": "what changed?",
        },
    }

    assert server.process_update(update) is True
    from lib.telegram.draft_queue import read_drafts

    drafts = read_drafts(draft_queue_path)
    assert len(drafts) == 1
    assert drafts[0].kind == "guarded_reply"
    assert drafts[0].topic == "drafts"
    assert drafts[0].status == "pending_confirmation"
    assert "what changed?" in drafts[0].body


def test_process_update_records_business_connection_and_queues_reply_draft(
    reload_server, monkeypatch, tmp_path
):
    draft_queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED", "1")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(draft_queue_path))
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("business message draft route must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    assert (
        server.process_update(
            {
                "update_id": 605,
                "business_connection": {
                    "id": "biz-1",
                    "user": {"id": 123, "username": "ari"},
                    "user_chat_id": 987,
                    "date": 1_774_000_000,
                    "is_enabled": True,
                    "rights": {"can_read_messages": True, "can_reply": True},
                },
            }
        )
        is True
    )
    assert (
        server.process_update(
            {
                "update_id": 606,
                "business_message": {
                    "business_connection_id": "biz-1",
                    "message_id": 9,
                    "chat": {"id": 987},
                    "from": {"id": 456},
                    "text": "reply to this customer",
                },
            }
        )
        is True
    )

    from lib.telegram.draft_queue import read_drafts

    drafts = read_drafts(draft_queue_path)
    assert [draft.kind for draft in drafts] == ["business_connection_audit", "guarded_reply"]
    assert drafts[0].metadata["business_connection_id"] == "biz-1"
    assert drafts[0].metadata["business_can_reply"] is True
    assert drafts[1].metadata["business_connection_id"] == "biz-1"
    assert drafts[1].metadata["business_connection_active"] is True
    assert drafts[1].metadata["business_can_reply"] is True
    assert drafts[1].metadata["business_can_read_messages"] is True
    assert "BusinessConnection.can_reply" in drafts[1].body


def test_process_update_blocks_payment_update_without_sending(reload_server, monkeypatch):
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("payment update must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 506,
        "pre_checkout_query": {"id": "pcq-1", "from": {"id": 123}},
    }

    assert server.process_update(update) is True


def test_process_update_ignores_unknown_callback_without_sending(reload_server, monkeypatch):
    server = reload_server()

    def fail_send(**_kwargs):
        raise AssertionError("unknown callback must not send Telegram messages")

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fail_send)

    update = {
        "update_id": 507,
        "callback_query": {
            "id": "callback-3",
            "from": {"id": 123},
            "data": "unknown:payload",
            "message": {"message_id": 77, "chat": {"id": -1001}},
        },
    }

    assert server.process_update(update) is False


# ---------------------------------------------------------------------------
# TelegramAPI._post error mapping
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, json_payload: Any | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_payload
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._json


def test_telegram_post_raises_on_http_error_with_redacted_body(reload_server, monkeypatch):
    server = reload_server()
    fake_token = "1234567890:abcdefghijklmnopqrstuvwxyzABCDE"
    server.TELEGRAM_API._token = fake_token

    response = _FakeResponse(
        status_code=409,
        json_payload=None,
        text=f"Conflict: another instance polling {fake_token}",
    )

    monkeypatch.setattr(server.requests, "post", lambda *a, **k: response)

    with pytest.raises(RuntimeError) as exc:
        server.TELEGRAM_API._post("getUpdates", {"offset": 0})

    msg = str(exc.value)
    assert fake_token not in msg
    assert "[REDACTED" in msg
    assert "status=409" in msg


def test_telegram_post_raises_when_api_returns_ok_false(reload_server, monkeypatch):
    server = reload_server()
    response = _FakeResponse(status_code=200, json_payload={"ok": False, "description": "boom"})
    monkeypatch.setattr(server.requests, "post", lambda *a, **k: response)

    with pytest.raises(RuntimeError, match="Telegram API error for sendMessage"):
        server.TELEGRAM_API._post("sendMessage", {"chat_id": 1, "text": "hi"})


def test_telegram_get_returns_result_dict(reload_server, monkeypatch):
    server = reload_server()

    monkeypatch.setattr(
        server.requests,
        "get",
        lambda *a, **k: _FakeResponse(
            status_code=200,
            json_payload={"ok": True, "result": {"username": "NemotronRariBot", "id": 123}},
        ),
    )

    assert server.TELEGRAM_API.get_me() == {"username": "NemotronRariBot", "id": 123}


def test_telegram_get_accepts_timeout_override(reload_server, monkeypatch):
    server = reload_server()
    captured: dict[str, Any] = {}

    def fake_get(url, timeout):
        captured["timeout"] = timeout
        return _FakeResponse(
            status_code=200,
            json_payload={"ok": True, "result": {"username": "NemotronRariBot"}},
        )

    monkeypatch.setattr(server.requests, "get", fake_get)

    assert server.TELEGRAM_API.get_me(timeout_seconds=1.25) == {"username": "NemotronRariBot"}
    assert captured["timeout"] == 1.25


def test_telegram_send_message_includes_disable_web_page_preview(reload_server, monkeypatch):
    server = reload_server()
    captured: dict = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(status_code=200, json_payload={"ok": True, "result": {}})

    monkeypatch.setattr(server.requests, "post", fake_post)

    server.TELEGRAM_API.send_message(chat_id=42, text="hello", parse_mode="HTML")

    assert captured["json"]["disable_web_page_preview"] is True
    assert captured["json"]["chat_id"] == 42
    assert captured["json"]["text"] == "hello"
    assert captured["json"]["parse_mode"] == "HTML"


def test_telegram_send_message_supports_reply_and_silent_delivery(reload_server, monkeypatch):
    server = reload_server()
    captured: dict[str, Any] = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _FakeResponse(status_code=200, json_payload={"ok": True, "result": {}})

    monkeypatch.setattr(server.requests, "post", fake_post)

    server.TELEGRAM_API.send_message(
        chat_id=42,
        text="hello",
        parse_mode="HTML",
        disable_notification=True,
        reply_parameters={"message_id": 99},
        message_thread_id=10,
        direct_messages_topic_id=11,
    )

    assert captured["json"]["disable_notification"] is True
    assert captured["json"]["reply_parameters"] == {"message_id": 99}
    assert captured["json"]["message_thread_id"] == 10
    assert captured["json"]["direct_messages_topic_id"] == 11


def test_telegram_send_message_supports_business_connection_id(reload_server, monkeypatch):
    server = reload_server()
    captured: dict[str, Any] = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _FakeResponse(status_code=200, json_payload={"ok": True, "result": {}})

    monkeypatch.setattr(server.requests, "post", fake_post)

    server.TELEGRAM_API.send_message(
        chat_id=42,
        text="hello",
        parse_mode=None,
        business_connection_id="biz-1",
    )

    assert captured["json"]["business_connection_id"] == "biz-1"


def test_telegram_send_message_omits_parse_mode_when_none(reload_server, monkeypatch):
    server = reload_server()
    captured: dict = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _FakeResponse(status_code=200, json_payload={"ok": True, "result": {}})

    monkeypatch.setattr(server.requests, "post", fake_post)

    server.TELEGRAM_API.send_message(chat_id=1, text="x", parse_mode=None)

    assert "parse_mode" not in captured["json"]


def test_telegram_get_updates_filters_non_dict_results(reload_server, monkeypatch):
    server = reload_server()

    def fake_post(*a, **k):
        return _FakeResponse(
            status_code=200,
            json_payload={
                "ok": True,
                "result": [
                    {"update_id": 1, "message": {"text": "a"}},
                    "not-a-dict",
                    None,
                    {"update_id": 2, "message": {"text": "b"}},
                ],
            },
        )

    monkeypatch.setattr(server.requests, "post", fake_post)

    updates = server.TELEGRAM_API.get_updates(offset=0)

    assert [u["update_id"] for u in updates] == [1, 2]


def test_telegram_get_updates_requests_supported_update_types(reload_server, monkeypatch):
    server = reload_server()
    captured: dict[str, Any] = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _FakeResponse(status_code=200, json_payload={"ok": True, "result": []})

    monkeypatch.setattr(server.requests, "post", fake_post)

    server.TELEGRAM_API.get_updates(offset=5)

    assert captured["json"]["allowed_updates"] == server._SUPPORTED_UPDATE_TYPES


def test_telegram_get_updates_returns_empty_when_result_not_list(reload_server, monkeypatch):
    server = reload_server()
    monkeypatch.setattr(
        server.requests,
        "post",
        lambda *a, **k: _FakeResponse(
            status_code=200, json_payload={"ok": True, "result": "unexpected"}
        ),
    )

    assert server.TELEGRAM_API.get_updates(offset=0) == []


def test_telegram_delete_webhook_passes_drop_pending_flag(reload_server, monkeypatch):
    server = reload_server()
    captured: dict = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(status_code=200, json_payload={"ok": True, "result": True})

    monkeypatch.setattr(server.requests, "post", fake_post)

    server.TELEGRAM_API.delete_webhook(drop_pending_updates=True)

    assert captured["url"].endswith("/deleteWebhook")
    assert captured["json"] == {"drop_pending_updates": True}


def test_telegram_delete_webhook_default_drop_pending_is_false(reload_server, monkeypatch):
    server = reload_server()
    captured: dict = {}
    monkeypatch.setattr(
        server.requests,
        "post",
        lambda url, json, timeout: (
            captured.update({"json": json}),
            _FakeResponse(status_code=200, json_payload={"ok": True, "result": True}),
        )[1],
    )

    server.TELEGRAM_API.delete_webhook()

    assert captured["json"] == {"drop_pending_updates": False}


def test_build_webhook_registration_payload_requires_https(reload_server):
    server = reload_server()

    with pytest.raises(ValueError, match="HTTPS"):
        server.build_webhook_registration_payload(url="http://example.invalid/telegram/webhook")


def test_telegram_set_webhook_payload_is_bot_api_safe(reload_server, monkeypatch):
    server = reload_server()
    captured: dict = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(status_code=200, json_payload={"ok": True, "result": True})

    monkeypatch.setattr(server.requests, "post", fake_post)

    server.TELEGRAM_API.set_webhook(
        url="https://example.invalid/telegram/webhook",
        secret_token="secret-token",
        drop_pending_updates=False,
    )

    assert captured["url"].endswith("/setWebhook")
    assert captured["json"] == {
        "url": "https://example.invalid/telegram/webhook",
        "allowed_updates": server._SUPPORTED_UPDATE_TYPES,
        "drop_pending_updates": False,
        "secret_token": "secret-token",
    }


def test_sanitized_webhook_registration_plan_omits_secret(reload_server):
    server = reload_server()

    plan = server.sanitized_webhook_registration_plan(
        url="https://example.invalid/telegram/webhook",
        secret_token_configured=True,
    )

    assert plan["method"] == "setWebhook"
    assert plan["secret_token_configured"] is True
    assert "secret_token" not in plan
    assert plan["allowed_updates"] == server._SUPPORTED_UPDATE_TYPES


# ---------------------------------------------------------------------------
# _validate_startup_config
# ---------------------------------------------------------------------------


def test_validate_startup_raises_when_no_token(reload_server, monkeypatch):
    """If somehow SETTINGS.token is empty at runtime, validation must refuse to start."""
    server = reload_server()

    # Force the token to empty post-import.
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token="",
            webhook_secret="",
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
        ),
    )

    with pytest.raises(RuntimeError, match="bot token is required"):
        server._validate_startup_config()


def test_validate_startup_raises_for_unsupported_mode(reload_server, monkeypatch):
    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token="abc",
            webhook_secret="",
            mode="unknown",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
        ),
    )

    with pytest.raises(RuntimeError, match="Unsupported MODE"):
        server._validate_startup_config()


def test_validate_startup_accepts_polling_mode(reload_server, monkeypatch):
    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token="abc",
            webhook_secret="",
            mode="polling",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
            token_source="explicit_env",
        ),
    )

    # No exception expected
    server._validate_startup_config()


def test_validate_startup_rejects_shared_token_polling(reload_server, monkeypatch):
    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token="abc",
            webhook_secret="",
            mode="polling",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
            token_source="shared_secret_file",
            shared_polling_allowed=False,
        ),
    )

    with pytest.raises(RuntimeError, match="Polling mode requires SAPPHIRE_PM_BOT_TOKEN"):
        server._validate_startup_config()


def test_validate_startup_break_glass_allows_shared_token_polling(reload_server, monkeypatch):
    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token="abc",
            webhook_secret="",
            mode="polling",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
            token_source="shared_env",
            shared_polling_allowed=True,
        ),
    )

    server._validate_startup_config()


# ---------------------------------------------------------------------------
# Settings.from_env
# ---------------------------------------------------------------------------


def test_settings_from_env_reads_default_port_and_host(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "xyz")
    monkeypatch.delenv("SAPPHIRE_PM_BOT_PORT", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_HOST", raising=False)
    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_PROBE_TIMEOUT_SECONDS", raising=False)
    server = reload_server()
    s = server.Settings.from_env()
    assert s.port == 18082
    assert s.host == "127.0.0.1"
    assert s.mode == "webhook"
    assert s.telegram_timeout_seconds == 30.0
    assert s.telegram_probe_timeout_seconds == 2.0


def test_settings_from_env_reads_probe_timeout(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "xyz")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_PROBE_TIMEOUT_SECONDS", "1.5")
    server = reload_server()
    s = server.Settings.from_env()
    assert s.telegram_probe_timeout_seconds == 1.5


def test_settings_from_env_handles_blank_port_string(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "xyz")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_PORT", "   ")
    server = reload_server()
    s = server.Settings.from_env()
    assert s.port == 18082  # blank string falls back to default


def test_settings_from_env_lowercases_mode(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "xyz")
    monkeypatch.setenv("MODE", "POLLING")
    server = reload_server()
    s = server.Settings.from_env()
    assert s.mode == "polling"


def test_settings_from_env_reports_token_source_and_polling_override(reload_server, monkeypatch):
    monkeypatch.delenv("SAPPHIRE_PM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "shared-token")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING", "yes")
    server = reload_server()
    s = server.Settings.from_env()
    assert s.token == "shared-token"
    assert s.token_source == "shared_env"
    assert s.shared_polling_allowed is True


def test_settings_from_env_reads_webhook_url(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_WEBHOOK_URL", "https://example.invalid/telegram/webhook")
    server = reload_server()
    s = server.Settings.from_env()
    assert s.webhook_url == "https://example.invalid/telegram/webhook"


def test_settings_from_env_reads_agent_scope_ids(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_AGENT_CHAT_IDS", "-1001, -1002 -1001")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_AGENT_THREAD_IDS", "7,9")
    server = reload_server()
    s = server.Settings.from_env()
    assert s.agent_allowed_chat_ids == (-1001, -1002)
    assert s.agent_allowed_thread_ids == (7, 9)


def test_settings_from_env_rejects_invalid_agent_scope_ids(reload_server, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_AGENT_CHAT_IDS", "-1001, nope")

    with pytest.raises(ValueError, match="SAPPHIRE_PM_BOT_AGENT_CHAT_IDS"):
        reload_server()


# ---------------------------------------------------------------------------
# health endpoint shape
# ---------------------------------------------------------------------------


def test_runtime_probe_uses_dedicated_probe_timeout(reload_server, monkeypatch):
    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token=server.SETTINGS.token,
            webhook_secret="",
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
            telegram_probe_timeout_seconds=1.5,
        ),
    )
    server._TELEGRAM_PROBE_CACHE["expires_at"] = 0.0
    server._TELEGRAM_PROBE_CACHE["value"] = None
    captured_timeouts: list[float] = []

    def fake_get(url, timeout):
        captured_timeouts.append(timeout)
        if url.endswith("/getMe"):
            return _FakeResponse(
                status_code=200,
                json_payload={"ok": True, "result": {"username": "NemotronRariBot", "id": 123}},
            )
        return _FakeResponse(
            status_code=200,
            json_payload={
                "ok": True,
                "result": {
                    "url": "https://example.invalid/telegram/webhook",
                    "pending_update_count": 2,
                    "allowed_updates": ["message"],
                },
            },
        )

    monkeypatch.setattr(server.requests, "get", fake_get)

    result = server._telegram_runtime_probe()

    assert captured_timeouts == [1.5, 1.5]
    assert result["probe_ok"] is True
    assert result["bot_username"] == "NemotronRariBot"
    assert result["delivery_ready"] is True


def test_runtime_probe_detects_expected_webhook_url_mismatch(reload_server, monkeypatch):
    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token=server.SETTINGS.token,
            webhook_secret="",
            webhook_url="https://expected.example/telegram/webhook",
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
            telegram_probe_timeout_seconds=1.5,
        ),
    )
    server._TELEGRAM_PROBE_CACHE["expires_at"] = 0.0
    server._TELEGRAM_PROBE_CACHE["value"] = None

    def fake_get(url, timeout):
        if url.endswith("/getMe"):
            return _FakeResponse(
                status_code=200,
                json_payload={"ok": True, "result": {"username": "SapphirePMBot", "id": 123}},
            )
        return _FakeResponse(
            status_code=200,
            json_payload={
                "ok": True,
                "result": {
                    "url": "https://other.example/telegram/webhook",
                    "pending_update_count": 0,
                    "allowed_updates": ["message"],
                },
            },
        )

    monkeypatch.setattr(server.requests, "get", fake_get)

    result = server._telegram_runtime_probe()

    assert result["webhook_registered"] is True
    assert result["webhook_url_configured"] is True
    assert result["webhook_url_matches_expected"] is False
    assert result["delivery_ready"] is False
    assert result["delivery_mode_reason"] == "webhook_url_mismatch"


def test_health_endpoint_full_shape_default_state(monkeypatch, tmp_path, reload_server):
    """Health response includes status, service name, mode, polling state, and
    webhook-secret-configured flag. Force HOME away from the dev box's real
    secrets dir so the fallback file readers don't pick up a real token.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HOME", str(tmp_path))
    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token=server.SETTINGS.token,
            webhook_secret="",
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
        ),
    )
    monkeypatch.setattr(
        server,
        "_telegram_runtime_probe",
        lambda: {
            "probe_ok": True,
            "bot_username": "NemotronRariBot",
            "bot_id": 123,
            "webhook_registered": False,
            "pending_update_count": 0,
            "allowed_updates": ["message", "edited_message"],
            "delivery_ready": False,
            "delivery_mode_reason": "webhook_missing",
            "probe_error": None,
        },
    )

    with TestClient(server.app) as http:
        response = http.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported_update_types"] == server._SUPPORTED_UPDATE_TYPES
    body = response.json()
    assert body["status"] == "degraded"
    assert body["service"] == "sapphire-pm-bot"
    assert body["local_process_ready"] is True
    assert body["mode"] == "webhook"
    assert body["token_source"] == "explicit_env"
    assert body["telegram_token_role"] == "dedicated"
    assert body["telegram_polling_policy"] == "dedicated_polling_allowed"
    assert body["polling_active"] is False
    assert body["last_poll_error"] is None
    assert body["shared_polling_allowed"] is False
    assert body["webhook_secret_configured"] is False
    assert body["agent_chat_scope_configured"] is False
    assert body["agent_chat_scope_count"] == 0
    assert body["agent_thread_scope_configured"] is False
    assert body["agent_thread_scope_count"] == 0
    assert body["bot_username"] == "NemotronRariBot"
    assert body["telegram_delivery_ready"] is False
    assert body["telegram_delivery_reason"] == "webhook_missing"
    assert body["telegram_inbound_owner"] == "pm_bot_webhook_unregistered"
    assert body["telegram_operator_action"] == "register_pm_bot_webhook"
    assert body["telegram_probe_ok"] is True
    assert body["telegram_webhook_registered"] is False
    assert body["telegram_pending_update_count"] == 0
    assert body["telegram_allowed_updates"] == ["message", "edited_message"]


def test_health_explains_shared_token_webhook_half_state(reload_server, monkeypatch):
    from fastapi.testclient import TestClient

    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token="abc",
            webhook_secret="secret",
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
            token_source="shared_secret_file",
            shared_polling_allowed=False,
        ),
    )
    monkeypatch.setattr(
        server,
        "_telegram_runtime_probe",
        lambda: {
            "probe_ok": True,
            "bot_username": "NemotronRariBot",
            "bot_id": 123,
            "webhook_registered": False,
            "pending_update_count": 0,
            "allowed_updates": ["message"],
            "delivery_ready": False,
            "delivery_mode_reason": "webhook_missing",
            "probe_error": None,
        },
    )

    with TestClient(server.app) as http:
        response = http.get("/health")

    body = response.json()
    assert body["status"] == "degraded"
    assert body["local_process_ready"] is True
    assert body["telegram_token_role"] == "shared"
    assert body["telegram_polling_policy"] == "shared_polling_disabled"
    assert body["telegram_inbound_owner"] == "pm_bot_webhook_unregistered"
    assert (
        body["telegram_operator_action"]
        == "register_pm_bot_webhook_or_leave_shared_token_to_external_poller"
    )


def test_telegram_ownership_endpoint_surfaces_group_readiness_blockers(
    reload_server,
    monkeypatch,
):
    from fastapi.testclient import TestClient

    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token="abc",
            webhook_secret="secret",
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
            token_source="shared_secret_file",
            shared_polling_allowed=False,
        ),
    )
    monkeypatch.setattr(
        server,
        "_telegram_runtime_probe",
        lambda: {
            "probe_ok": True,
            "bot_username": "NemotronRariBot",
            "bot_id": 123,
            "webhook_registered": False,
            "pending_update_count": 0,
            "allowed_updates": ["message"],
            "delivery_ready": False,
            "delivery_mode_reason": "webhook_missing",
            "probe_error": None,
        },
    )

    with TestClient(server.app) as http:
        response = http.get("/telegram/ownership")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_group_ready"] is False
    assert body["agent_group_blockers"] == ["webhook_missing", "agent_chat_scope_unconfigured"]
    assert body["single_ingress_owner"] == "pm_bot_webhook_unregistered"
    assert (
        body["operator_action"]
        == "register_pm_bot_webhook_or_leave_shared_token_to_external_poller"
    )
    assert body["no_send_router_guard"] == "only command routes may call sendMessage"
    assert body["agent_scope"] == {
        "chat_scope_configured": False,
        "chat_scope_count": 0,
        "thread_scope_configured": False,
        "thread_scope_count": 0,
    }
    assert (
        "keep_kimi_relay_disabled_until_private_operator_group_exists"
        in body["required_before_group"]
    )


def test_telegram_secretary_endpoint_reports_business_readiness(
    reload_server,
    monkeypatch,
):
    from fastapi.testclient import TestClient

    server = reload_server()
    monkeypatch.setattr(
        server,
        "_telegram_runtime_probe",
        lambda: {
            "probe_ok": True,
            "bot_username": "SapphirePMBot",
            "bot_id": 123,
            "webhook_registered": True,
            "webhook_url_configured": True,
            "webhook_url_matches_expected": True,
            "pending_update_count": 0,
            "allowed_updates": server._SUPPORTED_UPDATE_TYPES,
            "delivery_ready": True,
            "delivery_mode_reason": "webhook_registered",
            "probe_error": None,
        },
    )
    server.process_update(
        {
            "update_id": 991,
            "business_connection": {
                "id": "biz-1",
                "user": {"id": 42},
                "user_chat_id": 4200,
                "date": 1_774_000_000,
                "is_enabled": True,
                "rights": {"can_read_messages": True, "can_reply": True},
            },
        }
    )

    with TestClient(server.app) as http:
        response = http.get("/telegram/secretary")

    assert response.status_code == 200
    body = response.json()
    assert body["secretary_mode_ready"] is True
    assert body["secretary_mode_blockers"] == []
    assert body["can_reply_observed"] is True
    assert body["reply_policy"] == "draft_only_until_operator_approved"
    assert body["business_connections"] == {
        "observed_connection_count": 1,
        "active_connection_count": 1,
        "reply_capable_connection_count": 1,
        "latest_update_id": 991,
    }


def test_health_reports_polling_active_when_thread_alive(reload_server):
    from fastapi.testclient import TestClient

    server = reload_server()

    class _StubAliveThread:
        def is_alive(self):
            return True

    # Make the alive check pass: monkeypatch state's "thread" with a fake.
    # Use real threading.Thread instance to satisfy isinstance check.
    import threading

    real_thread = threading.Thread(target=lambda: None)
    real_thread.start()
    real_thread.join()
    # ``_StubAliveThread`` won't pass isinstance(threading.Thread); use a Thread that's daemon and never starts:
    # easier — patch is_alive on a real Thread.
    fake = threading.Thread(target=lambda: None)
    fake.is_alive = lambda: True  # type: ignore[method-assign]
    server.POLLING_STATE["thread"] = fake

    try:
        with TestClient(server.app) as http:
            response = http.get("/health")
        body = response.json()
        assert body["polling_active"] is True
    finally:
        server.POLLING_STATE["thread"] = None


def test_health_reports_last_poll_error(reload_server):
    from fastapi.testclient import TestClient

    server = reload_server()
    server.POLLING_STATE["last_error"] = "redacted error message"
    try:
        with TestClient(server.app) as http:
            response = http.get("/health")
        assert response.json()["last_poll_error"] == "redacted error message"
    finally:
        server.POLLING_STATE["last_error"] = None


def test_health_reports_probe_failure(reload_server, monkeypatch):
    from fastapi.testclient import TestClient

    server = reload_server()
    monkeypatch.setattr(
        server,
        "_telegram_runtime_probe",
        lambda: {
            "probe_ok": False,
            "bot_username": "",
            "bot_id": None,
            "webhook_registered": None,
            "pending_update_count": None,
            "allowed_updates": None,
            "delivery_ready": False,
            "delivery_mode_reason": "probe_failed",
            "probe_error": "timeout",
        },
    )

    with TestClient(server.app) as http:
        response = http.get("/health")

    body = response.json()
    assert body["telegram_probe_ok"] is False
    assert body["telegram_probe_error"] == "timeout"
    assert body["telegram_delivery_reason"] == "probe_failed"


# ---------------------------------------------------------------------------
# webhook handler — secret-not-configured branch
# ---------------------------------------------------------------------------


def test_webhook_with_no_secret_accepts_any_caller(reload_server, monkeypatch):
    """If webhook_secret is unset, the route must NOT 403 — it should still process."""
    from fastapi.testclient import TestClient

    server = reload_server()
    # Force webhook_secret to empty
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token=server.SETTINGS.token,
            webhook_secret="",  # unset
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
        ),
    )

    calls = []
    monkeypatch.setattr(server, "process_update", lambda upd: calls.append(upd) or True)

    update = {"message": {"chat": {"id": 1}, "text": "/ping"}}

    with TestClient(server.app) as http:
        response = http.post("/telegram/webhook", json=update)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "processed": True}
    assert calls == [update]


def test_webhook_returns_processed_false_when_handler_skips(reload_server, monkeypatch):
    """process_update returning False must surface as ``processed=False`` in the response."""
    from fastapi.testclient import TestClient

    server = reload_server()
    monkeypatch.setattr(
        server,
        "SETTINGS",
        server.Settings(
            token=server.SETTINGS.token,
            webhook_secret="",
            mode="webhook",
            host="127.0.0.1",
            port=18082,
            telegram_timeout_seconds=30.0,
        ),
    )
    monkeypatch.setattr(server, "process_update", lambda upd: False)

    with TestClient(server.app) as http:
        response = http.post("/telegram/webhook", json={"message": {"chat": {"id": 1}}})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "processed": False}


def test_get_updates_http_timeout_exceeds_long_poll_hold(reload_server, monkeypatch):
    """The HTTP read timeout must be longer than the getUpdates long-poll hold."""
    server = reload_server()
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "result": []}

    def fake_post(url, json=None, timeout=None):
        captured["timeout"] = timeout
        captured["poll_hold"] = json.get("timeout")
        return _Resp()

    monkeypatch.setattr(server.requests, "post", fake_post)
    client = server.TelegramAPI("dummy-token", timeout_seconds=30.0)
    client.get_updates(offset=0, timeout=30)

    assert captured["timeout"] > captured["poll_hold"]
