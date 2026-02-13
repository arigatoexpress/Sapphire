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

    ack_text = bot.send_message.await_args.args[0]
    assert "Session decision queued" in ack_text
    assert "Expected outcome:" in ack_text


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


def test_approve_all_command_dispatches_bulk_payload(telegram_module):
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
                    "text": "/approve_all clear backlog now",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "APPROVE_ALL_SESSIONS"
    assert quantity == 0.0

    payload = json.loads(symbol)
    assert payload["note"] == "clear backlog now"


def test_digest_builder_summarizes_and_groups_repeated_updates(telegram_module):
    lines = telegram_module.TelegramPlatformBot._build_digest_lines(
        [
            "📝 ⚡ Gemini Flash: Volatility remains within nominal bounds.",
            "📝 ⚡ Gemini Flash: Volatility remains within nominal bounds.",
            (
                "📢 💓 SAPPHIRE HEARTBEAT (scheduled)\n"
                "Active venues: ASTER, LIGHTER\n"
                "Paused/deallocated: none\n"
                "Kill switch: OFF\n"
                "Full autonomy: ON\n"
                "Failure pressure: 1\n\n"
                "Owner directive: none\n\n"
                "Reply with /status, /heartbeat, /focus."
            ),
        ]
    )

    assert any("Market pulse" in line and "x2" in line for line in lines)
    assert any("Heartbeat:" in line for line in lines)
    assert all("Reply with /status" not in line for line in lines)


def test_digest_builder_summarizes_autonomy_decision_brief(telegram_module):
    message = (
        "🚨 🤖 **AUTONOMY DECISION BRIEF**\n"
        "Session: `hook:autonomy:12345`\n"
        "Trigger: `failure_pressure`\n"
        "Why now: Failure pressure reached `5` (gate max `2`).\n"
        "Current state: active `ASTER` | paused `LIGHTER` | failure pressure `5` | pending `2` "
        "| DEX stage `staged_live` | DEX live `ON`\n"
        "Expected outcome: Triage root-cause failures, tighten guardrails, and stabilize dispatch reliability.\n"
        "Benefit vs current state: Lower error rate and safer autonomous throughput compared with current elevated "
        "incident pressure.\n"
        "Risk if deferred: Unresolved failures can cascade into venue deallocations or kill-switch events.\n"
        "Decision: `/approve <session_key> <note>` or `/reject <session_key> <reason>`\n"
        "Bulk option: `/approve_all <note>`"
    )
    lines = telegram_module.TelegramPlatformBot._build_digest_lines([message, message])

    assert any("Autonomy brief" in line and "x2" in line for line in lines)
    assert all("Expected outcome:" not in line for line in lines)


def test_trade_mode_command_dispatches_execution_toggle(telegram_module):
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
                    "text": "/trade on 0.03",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "ON"
    assert action == "SET_TRADING_EXECUTION"
    assert quantity == 0.03


def test_stage_command_dispatches_execution_stage_update(telegram_module):
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
                    "text": "/stage staged_live",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "staged_live"
    assert action == "SET_EXECUTION_STAGE"
    assert quantity == 0.0


def test_scout_status_command_dispatches_status_action(telegram_module):
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
                    "text": "/scout status",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "ALL"
    assert action == "SCOUT_STATUS"
    assert quantity == 0.0


def test_scout_register_command_dispatches_payload(telegram_module):
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
                    "text": "/scout register sapphire_scout Sapphire Scout",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "SCOUT_REGISTER"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["username"] == "sapphire_scout"
    assert payload["display_name"] == "Sapphire Scout"


def test_scout_publish_command_dispatches_payload(telegram_module):
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
                    "text": "/scout publish topic:TOPIC-00003 Push sanitized summary to external forum",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "SCOUT_PUBLISH"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["topic_id"] == "TOPIC-00003"
    assert "sanitized summary" in payload["body"]


def test_qty_command_dispatches_default_quantity_update(telegram_module):
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
                    "text": "/qty 0.05",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "ALL"
    assert action == "SET_TRADINGVIEW_DEFAULT_QUANTITY"
    assert quantity == 0.05


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

    ack_text = bot.send_message.await_args.args[0]
    assert "Heartbeat response captured and queued" in ack_text
    assert "Expected outcome:" in ack_text


def test_plain_text_status_routes_to_control_status(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "status please"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "ALL"
    assert action == "CONTROL_STATUS"
    assert quantity == 0.0

    ack_text = bot.send_message.await_args.args[0]
    assert "plain-text chat" in ack_text.lower()


def test_plain_text_manual_trade_routes_to_venue(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "aster buy 0.6 btc"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "ASTER"
    assert symbol == "BTC"
    assert action == "BUY"
    assert quantity == 0.6


def test_plain_text_fallback_routes_to_owner_steer(telegram_module):
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
                    "text": "let the agents prioritize reliability over speed this week",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "OWNER_STEER"
    assert quantity == 0.0
    assert "prioritize reliability" in symbol


def test_security_status_command_dispatches_action(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/security status"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "ALL"
    assert action == "SECURITY_STATUS"
    assert quantity == 0.0


def test_security_scan_command_dispatches_payload(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/security scan ci-cd no-upload"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "SECURITY_SCAN"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["skill"] == "ci-cd"
    assert payload["upload_if_missing"] is False


def test_media_status_command_dispatches_action(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/media status"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "ALL"
    assert action == "MEDIA_STATUS"
    assert quantity == 0.0


def test_media_mode_command_dispatches_payload(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/media mode owner_approval"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "MEDIA_SET_MODE"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["mode"] == "owner_approval"


def test_media_draft_command_dispatches_payload(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/media draft weekly execution insights"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "MEDIA_DRAFT"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["topic"] == "weekly execution insights"


def test_media_queue_command_dispatches_action(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/media queue"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert symbol == "ALL"
    assert action == "MEDIA_QUEUE_STATUS"
    assert quantity == 0.0


def test_media_publish_command_dispatches_payload(telegram_module):
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
                    "text": "/media publish topic:weekly alpha report targets:twitter,substack",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "MEDIA_PUBLISH"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["topic"] == "weekly alpha report"
    assert payload["targets"] == ["twitter", "substack"]


def test_media_approve_command_dispatches_payload(telegram_module):
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
                    "text": "/media approve media:1700000000:0001 ship now",
                }
            }
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "MEDIA_APPROVE"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["request_id"] == "media:1700000000:0001"
    assert payload["note"] == "ship now"


def test_media_reject_command_dispatches_payload(telegram_module):
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token",
        chat_id="12345",
        command_callback=callback,
    )
    bot.send_message = AsyncMock()

    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/media reject latest revise tone"}}
        )
    )

    callback.assert_awaited_once()
    platform, symbol, action, quantity = callback.await_args.args
    assert platform == "CONTROL"
    assert action == "MEDIA_REJECT"
    assert quantity == 0.0
    payload = json.loads(symbol)
    assert payload["request_id"] == "latest"
    assert payload["note"] == "revise tone"


def test_digest_builder_summarizes_structured_ack_messages(telegram_module):
    lines = telegram_module.TelegramPlatformBot._build_digest_lines(
        [
            (
                "🚨 🛡️ VirusTotal scan request queued.\n"
                "Scope: `all` | upload-on-miss: `NO`\n"
                "Expected outcome: skill verdict(s) with policy decision and report linkage.\n"
                "Benefit: blocks risky skill bundles before they impact autonomy."
            ),
            (
                "🚨 🛡️ VirusTotal scan request queued.\n"
                "Scope: `all` | upload-on-miss: `NO`\n"
                "Expected outcome: skill verdict(s) with policy decision and report linkage.\n"
                "Benefit: blocks risky skill bundles before they impact autonomy."
            ),
        ]
    )

    assert any("VirusTotal scan request queued" in line for line in lines)
    assert any("outcome" in line for line in lines)
    assert any("x2" in line for line in lines)


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


def test_tradingview_backtest_action_dispatches_workbench_request(autonomy_module, monkeypatch):
    plugin = autonomy_module.TradingViewAutonomyPlugin(_DummyMarketData(), default_chat_id="12345")

    async def fake_dispatch(action, payload, note, agent_id=""):
        return {
            "dispatched": True,
            "action": action,
            "payload": payload,
            "note": note,
            "agent_id": agent_id,
        }

    monkeypatch.setattr(plugin, "_dispatch_to_openclaw", fake_dispatch)

    result = asyncio.run(
        plugin.handle_action(
            "tv_backtest",
            {
                "strategy": "tv-aster-breakout",
                "symbol": "SOL",
                "timeframe": "15",
            },
        )
    )

    assert result["accepted"] == "backtest_requested"
    assert result["dispatch"]["dispatched"] is True
    assert result["dispatch"]["action"] == "tv_backtest"
    assert "workspace" in result
