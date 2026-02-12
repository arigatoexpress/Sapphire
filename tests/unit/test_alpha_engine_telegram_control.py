import importlib.util
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
TELEGRAM_BOT_PATH = ROOT_DIR / "services/alpha-engine/shared/telegram_bot.py"
AUTONOMY_PLUGIN_PATH = ROOT_DIR / "services/alpha-engine/src/integrations/tradingview_autonomy.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _DummyMarketData:
    def get_price(self, venue: str, symbol: str):
        return 100.0


@pytest.fixture(scope="module")
def telegram_module():
    return _load_module(TELEGRAM_BOT_PATH, "alpha_engine_telegram_bot")


@pytest.fixture(scope="module")
def autonomy_module():
    return _load_module(AUTONOMY_PLUGIN_PATH, "alpha_engine_tradingview_autonomy")


def test_approve_command_dispatches_session_payload(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/approve latest ship it"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "APPROVE_SESSION"
    assert quantity == 0.0

    payload = json.loads(symbol)
    assert payload["session_key"] == "latest"
    assert payload["note"] == "ship it"


def test_reject_command_dispatches_session_payload(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {
                "message": {
                    "chat": {"id": "12345"},
                    "text": "/reject hook:autonomy:1234 hold until risk is lower",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "REJECT_SESSION"
    assert quantity == 0.0

    payload = json.loads(symbol)
    assert payload["session_key"] == "hook:autonomy:1234"
    assert payload["note"] == "hold until risk is lower"


def test_answer_alias_still_routes_to_owner_steer(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/answer prioritize reliability over velocity"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "OWNER_STEER"
    assert quantity == 0.0
    assert "prioritize reliability" in symbol


def test_dispatch_session_decision_payload(autonomy_module, monkeypatch):
    plugin = autonomy_module.TradingViewAutonomyPlugin(_DummyMarketData(), default_chat_id="12345")

    async def fake_dispatch(action, payload, note, agent_id=""):
        return {
            "dispatched": True,
            "action": action,
            "payload": payload,
            "note": note,
            "agent_id": agent_id,
            "session_key": "dispatch-session-key",
        }

    monkeypatch.setattr(plugin, "_dispatch_to_openclaw", fake_dispatch)

    result = asyncio.run(
        plugin.dispatch_session_decision(
            session_key="hook:tradingview:abc123",
            decision="approve",
            note="looks good",
        )
    )

    assert result["dispatched"] is True
    assert result["action"] == "session_approve"
    assert result["payload"]["decision"] == "APPROVE"
    assert result["payload"]["session_key"] == "hook:tradingview:abc123"
    assert result["payload"]["note"] == "looks good"


def test_dispatch_session_decision_rejects_invalid_inputs(autonomy_module):
    plugin = autonomy_module.TradingViewAutonomyPlugin(_DummyMarketData(), default_chat_id="12345")

    missing_key = asyncio.run(
        plugin.dispatch_session_decision(
            session_key="",
            decision="approve",
            note="",
        )
    )
    assert missing_key["dispatched"] is False
    assert missing_key["reason"] == "session_key_missing"

    invalid_decision = asyncio.run(
        plugin.dispatch_session_decision(
            session_key="hook:one",
            decision="maybe",
            note="",
        )
    )
    assert invalid_decision["dispatched"] is False
    assert invalid_decision["reason"] == "invalid_decision"
