"""Tests for the standalone Telegram bot service safety surfaces."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
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


def test_health_command_uses_live_brief_profile(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)
    calls = []

    def sender(text: str, chat_id: str | None = None):
        calls.append((text, chat_id))
        return {"ok": True}

    requested = []

    def fake_run_tool(tool_script: str, input_data: dict | None = None) -> str:
        requested.append((tool_script, input_data))
        return json.dumps(
            {
                "overall": "RED",
                "summary": "1 green, 0 yellow, 1 red out of 2 checks",
                "services": {"dashboard:8080": {"status": "green", "detail": "401 auth"}},
                "data_freshness": {"trading_signals": {"status": "red", "detail": "243h old"}},
                "inference": {"mac_ollama": {"status": "green", "detail": "200 OK"}},
            }
        )

    monkeypatch.setattr(app, "run_tool_direct", fake_run_tool)

    result = app.handle_command("/health", "", "123", sender=sender)

    assert requested == [("health_check.py", {"profile": "brief"})]
    assert calls == [("🔬 Running live health check...", "123")]
    assert "trading_signals" in result
    assert "243h old" in result


def test_btc_command_uses_rolling_start_date(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)
    calls = []
    recent_start_date = app._recent_start_date

    monkeypatch.setattr(
        app,
        "_recent_start_date",
        lambda: recent_start_date(now=datetime(2026, 4, 28, tzinfo=UTC)),
    )
    monkeypatch.setattr(
        app,
        "run_tool_direct",
        lambda tool, payload=None: calls.append((tool, payload)) or "bars",
    )

    assert app.handle_command("/btc", "", "123") == "bars"
    assert calls == [
        (
            "market.py",
            {"action": "crypto", "symbol": "BTC-USD", "start_date": "2026-03-28"},
        )
    ]


def test_live_system_prompt_summarizes_stale_data_and_models(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)

    def fake_run_tool(tool_script: str, input_data: dict | None = None) -> str:
        if tool_script == "health_check.py":
            assert input_data == {"profile": "brief"}
            return json.dumps(
                {
                    "overall": "RED",
                    "summary": "8 green, 0 yellow, 3 red out of 11 checks",
                    "services": {"dashboard:8080": {"status": "green", "detail": "401 auth"}},
                    "data_freshness": {
                        "trading_predictions": {"status": "red", "detail": "83h old"}
                    },
                    "inference": {"mac_ollama": {"status": "green", "detail": "200 OK"}},
                }
            )
        if tool_script == "status.py":
            return json.dumps(
                {
                    "inference": {
                        "proxy_health": {"mac-local": "healthy", "windows-gpu": "degraded"},
                        "local_models": ["hermes3:8b", "nemotron-mini:4b"],
                        "gpu_models": [],
                    }
                }
            )
        raise AssertionError(tool_script)

    monkeypatch.setattr(app, "run_tool_direct", fake_run_tool)

    prompt = app.build_live_system_prompt()

    assert "Use the live context below as the only current operational truth" in prompt
    assert "trading_predictions" in prompt
    assert "83h old" in prompt
    assert "mac-local=healthy" in prompt
    assert "1,211" not in prompt
    assert "67%" not in prompt


def test_chat_with_hermes_sends_live_context_to_model(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)
    captured = {}

    monkeypatch.setattr(app, "build_live_system_prompt", lambda: "LIVE SNAPSHOT: stale=false")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "message": {"content": "Fresh answer"},
                    "eval_count": 12,
                    "eval_duration": 1_000_000_000,
                }
            ).encode()

    def fake_urlopen(req, timeout: int, context=None):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode())
        return FakeResponse()

    monkeypatch.setattr(app.urllib.request, "urlopen", fake_urlopen)

    result = app.chat_with_hermes("How is the system?", "123")

    assert captured["url"] == "http://100.71.10.48:11434/api/chat"
    assert captured["payload"]["messages"][0] == {
        "role": "system",
        "content": "LIVE SNAPSHOT: stale=false",
    }
    assert "Fresh answer" in result


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
