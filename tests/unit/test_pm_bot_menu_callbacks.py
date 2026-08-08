"""Tests for pm-bot menu callback answering + the heartbeat scheduler."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "plugins" / "claw-sapphire" / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


@pytest.fixture
def server(monkeypatch):
    """Import the pm-bot server with a dummy token so startup validation passes."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:dummy-token")
    monkeypatch.setenv("MODE", "webhook")
    module = importlib.import_module("services.pm_bot.server")
    importlib.reload(module)
    # Never touch the network.
    module.TELEGRAM_API = MagicMock()
    module._RECENT_UPDATE_IDS.clear()
    return module


def _callback_update(data: str, *, update_id: int = 500) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cbq-abc",
            "data": data,
            "from": {"id": 7, "username": "ari", "is_bot": False},
            "message": {"message_id": 55, "chat": {"id": 42}},
        },
    }


class TestMenuCallbackAnswering:
    def test_menu_callback_answers_and_edits(self, server):
        assert server.process_update(_callback_update("m:pf")) is True

        server.TELEGRAM_API.answer_callback_query.assert_called_once()
        assert (
            server.TELEGRAM_API.answer_callback_query.call_args.kwargs["callback_query_id"]
            == "cbq-abc"
        )

        server.TELEGRAM_API.edit_message_text.assert_called_once()
        edit = server.TELEGRAM_API.edit_message_text.call_args.kwargs
        assert edit["chat_id"] == 42
        assert edit["message_id"] == 55
        assert edit["parse_mode"] == "MarkdownV2"
        assert "inline_keyboard" in edit["reply_markup"]

    def test_menu_callback_never_calls_send_message(self, server):
        """Menus edit in place; they must not spam new messages."""
        server.process_update(_callback_update("m:sg"))
        server.TELEGRAM_API.send_message.assert_not_called()

    def test_edit_failure_is_swallowed(self, server):
        server.TELEGRAM_API.edit_message_text.side_effect = RuntimeError("message is not modified")
        # Re-tapping the same button must not crash the webhook handler.
        assert server.process_update(_callback_update("m:pf")) is False

    def test_answer_failure_still_attempts_edit(self, server):
        server.TELEGRAM_API.answer_callback_query.side_effect = RuntimeError("timeout")
        assert server.process_update(_callback_update("m:pf")) is True
        server.TELEGRAM_API.edit_message_text.assert_called_once()

    def test_home_callback_renders_full_menu(self, server):
        server.process_update(_callback_update("m:h"))
        markup = server.TELEGRAM_API.edit_message_text.call_args.kwargs["reply_markup"]
        buttons = [b for row in markup["inline_keyboard"] for b in row]
        assert len(buttons) >= 7

    def test_duplicate_update_is_ignored(self, server):
        server.process_update(_callback_update("m:pf", update_id=900))
        server.TELEGRAM_API.reset_mock()
        assert server.process_update(_callback_update("m:pf", update_id=900)) is False
        server.TELEGRAM_API.edit_message_text.assert_not_called()


class TestBlockedCallbacksUnchanged:
    def test_dangerous_callback_does_not_reach_menu_handler(self, server):
        server.process_update(_callback_update("trade:BTC"))
        server.TELEGRAM_API.edit_message_text.assert_not_called()
        server.TELEGRAM_API.send_message.assert_not_called()

    def test_unknown_callback_makes_no_external_call(self, server):
        server.process_update(_callback_update("mystery:thing"))
        server.TELEGRAM_API.send_message.assert_not_called()
        server.TELEGRAM_API.edit_message_text.assert_not_called()


class TestSettingsMutationThroughCallback:
    def test_heartbeat_toggle_persists(self, server, tmp_path, monkeypatch):
        settings_path = tmp_path / "telegram_settings.json"
        monkeypatch.setenv("SAPPHIRE_TELEGRAM_SETTINGS_PATH", str(settings_path))

        from lib.telegram import settings_store

        assert settings_store.load(settings_path).heartbeat_enabled is False
        server.process_update(_callback_update("m:cfg:hb:on"))
        assert settings_store.load(settings_path).heartbeat_enabled is True

    def test_toggle_answers_with_confirmation_toast(self, server, tmp_path, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_TELEGRAM_SETTINGS_PATH", str(tmp_path / "s.json"))
        server.process_update(_callback_update("m:cfg:hb:on"))
        toast = server.TELEGRAM_API.answer_callback_query.call_args.kwargs["text"]
        assert "Heartbeat enabled" in toast


class TestSendMessageSupportsKeyboard:
    def test_reply_markup_forwarded_when_handler_provides_one(self, server, monkeypatch):
        import sapphire_pm_bot

        monkeypatch.setattr(
            sapphire_pm_bot,
            "handle_telegram_command",
            lambda update: {
                "text": "hi",
                "parse_mode": "MarkdownV2",
                "reply_markup": {"inline_keyboard": [[{"text": "a", "callback_data": "m:h"}]]},
            },
        )
        update = {
            "update_id": 601,
            "message": {
                "message_id": 1,
                "chat": {"id": 42},
                "from": {"id": 7, "username": "ari"},
                "text": "/menu",
            },
        }
        assert server.process_update(update) is True
        kwargs = server.TELEGRAM_API.send_message.call_args.kwargs
        assert kwargs["reply_markup"]["inline_keyboard"]

    def test_absent_reply_markup_passes_none(self, server, monkeypatch):
        import sapphire_pm_bot

        monkeypatch.setattr(
            sapphire_pm_bot,
            "handle_telegram_command",
            lambda update: {"text": "hi", "parse_mode": None},
        )
        update = {
            "update_id": 602,
            "message": {
                "message_id": 1,
                "chat": {"id": 42},
                "from": {"id": 7, "username": "ari"},
                "text": "/whoami",
            },
        }
        server.process_update(update)
        assert server.TELEGRAM_API.send_message.call_args.kwargs["reply_markup"] is None


class TestHeartbeatScheduling:
    @pytest.mark.parametrize(
        "hour,interval,expected",
        [
            (0, 4, True),
            (4, 4, True),
            (5, 4, False),
            (12, 12, True),
            (13, 12, False),
            (0, 24, True),
            (1, 24, False),
        ],
    )
    def test_due_alignment(self, hour, interval, expected):
        from lib.telegram import heartbeat

        assert heartbeat._due(hour, interval) is expected

    def test_zero_interval_never_fires(self):
        from lib.telegram import heartbeat

        assert heartbeat._due(0, 0) is False

    def test_disabled_heartbeat_skips_send(self, tmp_path, monkeypatch):
        from lib.telegram import heartbeat, settings_store

        monkeypatch.setenv("SAPPHIRE_TELEGRAM_SETTINGS_PATH", str(tmp_path / "s.json"))
        monkeypatch.setattr(heartbeat, "STATE_FILE", tmp_path / "state.json")
        called = []
        monkeypatch.setattr(heartbeat, "_run_notify", lambda *a, **k: called.append(1) or 0)
        settings_store.save(settings_store.TelegramSettings(heartbeat_enabled=False))

        assert heartbeat.run_once() == 0
        assert called == []

    def test_enabled_and_due_sends(self, tmp_path, monkeypatch):
        from datetime import UTC, datetime

        from lib.telegram import heartbeat, settings_store

        monkeypatch.setenv("SAPPHIRE_TELEGRAM_SETTINGS_PATH", str(tmp_path / "s.json"))
        monkeypatch.setattr(heartbeat, "STATE_FILE", tmp_path / "state.json")
        sent: list[str] = []
        monkeypatch.setattr(heartbeat, "_run_notify", lambda text, **k: sent.append(text) or 0)
        settings_store.save(
            settings_store.TelegramSettings(heartbeat_enabled=True, heartbeat_hours=4)
        )

        aligned = datetime(2026, 7, 25, 4, 0, tzinfo=UTC)
        assert heartbeat.run_once(now=aligned) == 0
        assert len(sent) == 1
        assert "Sapphire OS" in sent[0]

    def test_enabled_but_not_due_skips(self, tmp_path, monkeypatch):
        from datetime import UTC, datetime

        from lib.telegram import heartbeat, settings_store

        monkeypatch.setenv("SAPPHIRE_TELEGRAM_SETTINGS_PATH", str(tmp_path / "s.json"))
        monkeypatch.setattr(heartbeat, "STATE_FILE", tmp_path / "state.json")
        sent: list[str] = []
        monkeypatch.setattr(heartbeat, "_run_notify", lambda text, **k: sent.append(text) or 0)
        settings_store.save(
            settings_store.TelegramSettings(heartbeat_enabled=True, heartbeat_hours=4)
        )

        unaligned = datetime(2026, 7, 25, 5, 0, tzinfo=UTC)
        assert heartbeat.run_once(now=unaligned) == 0
        assert sent == []
