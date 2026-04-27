"""Tests for the standalone Telegram bot service safety surfaces."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "services" / "telegram-bot" / "app.py"

TELEGRAM_ENV_VARS = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_DRY_RUN",
    "SAPPHIRE_PM_BOT_ALLOWED_USER_IDS",
    "ALLOWED_TELEGRAM_USER_IDS",
    "TELEGRAM_ALLOWED_USER_IDS",
)


def _load_app(monkeypatch, tmp_path: Path, **env: str) -> ModuleType:
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in TELEGRAM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    spec = importlib.util.spec_from_file_location(f"telegram_bot_app_{uuid4().hex}", APP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_without_secret_files_is_safe(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)

    assert app.BOT_TOKEN == ""
    assert app.CHAT_ID == ""
    assert app.ALLOWED_USERS == set()


def test_allowed_users_prefer_explicit_user_ids(monkeypatch, tmp_path):
    app = _load_app(
        monkeypatch,
        tmp_path,
        TELEGRAM_CHAT_ID="-100123",
        SAPPHIRE_PM_BOT_ALLOWED_USER_IDS="42, bad, 84",
    )

    assert app.ALLOWED_USERS == {42, 84}


def test_send_message_dry_run_never_calls_telegram(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path, TELEGRAM_DRY_RUN="1")

    def fail_tg_api(*_args, **_kwargs):
        raise AssertionError("dry-run send should not call Telegram")

    monkeypatch.setattr(app, "tg_api", fail_tg_api)

    result = app.send_message("hello", "123")

    assert result == {
        "ok": True,
        "dry_run": True,
        "method": "sendMessage",
        "chat_id": "123",
        "text_len": 5,
    }


def test_send_message_without_token_fails_closed(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)

    assert app.send_message("hello", "123") == {"ok": False, "error": "missing_bot_token"}


def test_handle_command_uses_injected_sender(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)
    calls = []

    def sender(text: str, chat_id: str | None = None):
        calls.append((text, chat_id))
        return {"ok": True}

    monkeypatch.setattr(app, "run_tool_direct", lambda *_args, **_kwargs: "done")

    result = app.handle_command("/dispatch", "ship dry-run patch", "123", sender=sender)

    assert result == "done"
    assert calls == [("🏭 Dispatching...", "123")]


def test_handle_message_unauthorized_uses_injected_sender(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)
    app.ALLOWED_USERS = {42}
    calls = []

    def sender(text: str, chat_id: str | None = None):
        calls.append((text, chat_id))
        return {"ok": True}

    app.handle_message(
        {"chat": {"id": 123}, "from": {"id": 7}, "text": "/status"},
        sender=sender,
    )

    assert len(calls) == 1
    assert "Unauthorized" in calls[0][0]
    assert calls[0][1] == "123"


def test_handle_message_unknown_command_uses_injected_sender(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)
    app.ALLOWED_USERS = {42}
    calls = []

    def sender(text: str, chat_id: str | None = None):
        calls.append((text, chat_id))
        return {"ok": True}

    app.handle_message(
        {"chat": {"id": 123}, "from": {"id": 42}, "text": "/wat"},
        sender=sender,
    )

    assert calls == [("Unknown command: `/wat`. Use /help.", "123")]
