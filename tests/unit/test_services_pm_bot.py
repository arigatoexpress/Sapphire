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
    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token-default")

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

    def fake_send_message(*, chat_id, text, parse_mode):
        sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return {"ok": True}

    monkeypatch.setattr(server.TELEGRAM_API, "send_message", fake_send_message)

    update = {"update_id": 9, "message": {"chat": {"id": 77}, "text": "/help"}}
    assert server.process_update(update) is True
    assert sent == [{"chat_id": 77, "text": "PONG", "parse_mode": "Markdown"}]


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


def test_process_update_returns_false_when_handler_returns_empty_text(
    reload_server, monkeypatch
):
    server = reload_server()
    if str(TOOL_DIR) not in sys.path:
        sys.path.insert(0, str(TOOL_DIR))
    import sapphire_pm_bot

    monkeypatch.setattr(
        sapphire_pm_bot, "handle_telegram_command", lambda upd: {"text": "   "}
    )
    sent: list[dict] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    update = {"message": {"chat": {"id": 8}, "text": "/noop"}}
    assert server.process_update(update) is False
    assert sent == []


def test_process_update_returns_false_for_non_dict_payload(reload_server, monkeypatch):
    server = reload_server()
    sent: list[dict] = []
    monkeypatch.setattr(server.TELEGRAM_API, "send_message", lambda **kw: sent.append(kw))

    # message is not a dict — process_update should bail
    assert server.process_update({"update_id": 1, "message": "not-a-dict"}) is False
    assert sent == []


# ---------------------------------------------------------------------------
# TelegramAPI._post error mapping
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(
        self, *, status_code: int = 200, json_payload: Any | None = None, text: str = ""
    ):
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
        ),
    )

    # No exception expected
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
    server = reload_server()
    s = server.Settings.from_env()
    assert s.port == 18082
    assert s.host == "127.0.0.1"
    assert s.mode == "webhook"
    assert s.telegram_timeout_seconds == 30.0


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


# ---------------------------------------------------------------------------
# health endpoint shape
# ---------------------------------------------------------------------------


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

    with TestClient(server.app) as http:
        response = http.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "sapphire-pm-bot"
    assert body["mode"] == "webhook"
    assert body["polling_active"] is False
    assert body["last_poll_error"] is None
    assert body["webhook_secret_configured"] is False


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
