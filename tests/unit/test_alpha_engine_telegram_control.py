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
    assert "Approved" in ack_text or "Obsidian" in ack_text


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


def test_scout_publish_comment_command_dispatches_post_id_payload(telegram_module):
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
                    "text": "/scout publish topic:TOPIC-00003 post:abc123 Push follow-up comment",
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
    assert payload["post_id"] == "abc123"
    assert payload["body"] == "Push follow-up comment"


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
    assert "reply" in ack_text.lower() or "cycle" in ack_text.lower()


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
    assert "sapphire" in ack_text.lower() or "status" in ack_text.lower()


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


def test_plain_text_scout_comment_routes_with_post_id(telegram_module):
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
                    "text": "scout publish topic:TOPIC-00003 post:abc123 publish this as a comment",
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
    assert payload["post_id"] == "abc123"
    assert payload["body"] == "publish this as a comment"


def test_plain_text_fallback_routes_to_owner_chat(telegram_module):
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
    assert action == "OWNER_CHAT"
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


# ── Phase 3: Forum Telegram command parsing ────────────────────


def test_forum_top_slash_command(telegram_module):
    """'/forum top' dispatches FORUM_TOP_TOPICS."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/forum top"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "FORUM_TOP_TOPICS"
    payload = json.loads(symbol)
    assert payload["limit"] == 10


def test_forum_top_with_category(telegram_module):
    """'/forum top trade_idea' passes category filter."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/forum top trade_idea"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "FORUM_TOP_TOPICS"
    payload = json.loads(symbol)
    assert payload["category"] == "trade_idea"


def test_forum_vote_slash_command(telegram_module):
    """'/forum vote TOPIC-00001 up' dispatches FORUM_VOTE_TOPIC."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/forum vote TOPIC-00001 up"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "FORUM_VOTE_TOPIC"
    payload = json.loads(symbol)
    assert payload["topic_id"] == "TOPIC-00001"
    assert payload["direction"] == "up"


def test_forum_agents_slash_command(telegram_module):
    """'/forum agents' dispatches FORUM_AGENTS."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/forum agents"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "FORUM_AGENTS"


def test_forum_thread_slash_command(telegram_module):
    """'/forum thread TOPIC-00005' dispatches FORUM_THREAD."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/forum thread TOPIC-00005"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "FORUM_THREAD"
    payload = json.loads(symbol)
    assert payload["topic_id"] == "TOPIC-00005"


def test_forum_post_slash_command(telegram_module):
    """'/forum post Title | Body category:trade_idea' dispatches FORUM_CREATE_TOPIC."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/forum post SOL breakout setup | BTC correlation divergence suggests SOL upside category:trade_idea"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "FORUM_CREATE_TOPIC"
    payload = json.loads(symbol)
    assert payload["title"] == "SOL breakout setup"
    assert "BTC correlation" in payload["body"]
    assert payload["category"] == "trade_idea"


def test_forum_top_plain_text(telegram_module):
    """Plain text 'forum top' dispatches FORUM_TOP_TOPICS."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("forum top")
    assert result is not None
    assert result["action"] == "FORUM_TOP_TOPICS"


def test_forum_vote_plain_text(telegram_module):
    """Plain text 'forum vote TOPIC-00001 down' dispatches FORUM_VOTE_TOPIC."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("forum vote TOPIC-00001 down")
    assert result is not None
    assert result["action"] == "FORUM_VOTE_TOPIC"
    payload = json.loads(result["symbol"])
    assert payload["direction"] == "down"


def test_forum_agents_plain_text(telegram_module):
    """Plain text 'forum agents' dispatches FORUM_AGENTS."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("forum agents")
    assert result is not None
    assert result["action"] == "FORUM_AGENTS"


def test_forum_thread_plain_text(telegram_module):
    """Plain text 'forum thread TOPIC-00003' dispatches FORUM_THREAD."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("forum thread TOPIC-00003")
    assert result is not None
    assert result["action"] == "FORUM_THREAD"
    payload = json.loads(result["symbol"])
    assert payload["topic_id"] == "TOPIC-00003"


def test_forum_approvals_slash_command(telegram_module):
    """'/forum approvals' dispatches FORUM_PENDING_APPROVALS."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/forum approvals"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "FORUM_PENDING_APPROVALS"


def test_forum_approvals_plain_text(telegram_module):
    """Plain text 'forum approvals' dispatches FORUM_PENDING_APPROVALS."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("forum approvals")
    assert result is not None
    assert result["action"] == "FORUM_PENDING_APPROVALS"


# ── Phase 4: Reputation Telegram Commands ────────────────────────


def test_rep_leaderboard_slash_command(telegram_module):
    """'/rep leaderboard' dispatches REP_LEADERBOARD."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/rep leaderboard"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "REP_LEADERBOARD"


def test_rep_leaderboard_with_limit(telegram_module):
    """'/rep leaderboard 5' passes limit in payload."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/rep leaderboard 5"}}
        )
    )
    callback.assert_awaited_once()
    platform, symbol, action, _ = callback.await_args.args
    assert action == "REP_LEADERBOARD"
    payload = json.loads(symbol)
    assert payload["limit"] == 5


def test_rep_info_slash_command(telegram_module):
    """'/rep info BOT_ALPHA' dispatches REP_BOT_INFO."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/rep info BOT_ALPHA"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "REP_BOT_INFO"
    payload = json.loads(symbol)
    assert payload["bot_id"] == "BOT_ALPHA"


def test_rep_count_slash_command(telegram_module):
    """'/rep count' dispatches REP_BOT_COUNT."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/rep count"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "REP_BOT_COUNT"


def test_rep_ban_slash_command(telegram_module):
    """'/rep ban BOT_EVIL spam bot' dispatches REP_BAN_BOT."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/rep ban BOT_EVIL spam bot"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "REP_BAN_BOT"
    payload = json.loads(symbol)
    assert payload["bot_id"] == "BOT_EVIL"
    assert payload["reason"] == "spam bot"


def test_rep_penalize_slash_command(telegram_module):
    """'/rep penalize BOT_BAD low quality' dispatches REP_PENALIZE_BOT."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/rep penalize BOT_BAD low quality"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "REP_PENALIZE_BOT"
    payload = json.loads(symbol)
    assert payload["bot_id"] == "BOT_BAD"
    assert payload["reason"] == "low quality"


def test_rep_leaderboard_plain_text(telegram_module):
    """Plain text 'rep leaderboard' dispatches REP_LEADERBOARD."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("rep leaderboard")
    assert result is not None
    assert result["action"] == "REP_LEADERBOARD"


def test_rep_info_plain_text(telegram_module):
    """Plain text 'rep info BOT_TEST' dispatches REP_BOT_INFO."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("rep info BOT_TEST")
    assert result is not None
    assert result["action"] == "REP_BOT_INFO"
    payload = json.loads(result["symbol"])
    assert payload["bot_id"] == "BOT_TEST"


def test_rep_count_plain_text(telegram_module):
    """Plain text 'rep count' dispatches REP_BOT_COUNT."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("rep count")
    assert result is not None
    assert result["action"] == "REP_BOT_COUNT"


# ── Phase 4: Swarm Telegram Commands ────────────────────────────


def test_swarm_aggregate_slash_command(telegram_module):
    """'/swarm aggregate BTC/USDT' dispatches SWARM_AGGREGATE."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/swarm aggregate BTC/USDT"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "SWARM_AGGREGATE"
    payload = json.loads(symbol)
    assert payload["symbol"] == "BTC/USDT"


def test_swarm_ideas_slash_command(telegram_module):
    """'/swarm ideas ETH' dispatches SWARM_OPEN_IDEAS."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/swarm ideas ETH"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "SWARM_OPEN_IDEAS"
    payload = json.loads(symbol)
    assert payload["symbol"] == "ETH"


def test_swarm_ideas_no_symbol(telegram_module):
    """'/swarm ideas' dispatches SWARM_OPEN_IDEAS with empty symbol."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/swarm ideas"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "SWARM_OPEN_IDEAS"


def test_swarm_stats_slash_command(telegram_module):
    """'/swarm stats' dispatches SWARM_STATS."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/swarm stats"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "SWARM_STATS"


def test_swarm_aggregate_plain_text(telegram_module):
    """Plain text 'swarm aggregate SOL' dispatches SWARM_AGGREGATE."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("swarm aggregate SOL")
    assert result is not None
    assert result["action"] == "SWARM_AGGREGATE"
    payload = json.loads(result["symbol"])
    assert payload["symbol"] == "SOL"


def test_swarm_ideas_plain_text(telegram_module):
    """Plain text 'swarm ideas BTC' dispatches SWARM_OPEN_IDEAS."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("swarm ideas BTC")
    assert result is not None
    assert result["action"] == "SWARM_OPEN_IDEAS"


def test_swarm_stats_plain_text(telegram_module):
    """Plain text 'swarm stats' dispatches SWARM_STATS."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("swarm stats")
    assert result is not None
    assert result["action"] == "SWARM_STATS"


# ── Phase 4: Learning Telegram Commands ─────────────────────────


def test_learn_report_slash_command(telegram_module):
    """'/learn report' dispatches LEARN_REPORT."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/learn report"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "LEARN_REPORT"


def test_learn_summary_slash_command(telegram_module):
    """'/learn summary' dispatches LEARN_SUMMARY."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/learn summary"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "LEARN_SUMMARY"


def test_learn_bias_slash_command(telegram_module):
    """'/learn bias BTC LONG 1h' dispatches LEARN_BIAS with payload."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/learn bias BTC LONG 1h"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "LEARN_BIAS"
    payload = json.loads(symbol)
    assert payload["symbol"] == "BTC"
    assert payload["direction"] == "LONG"
    assert payload["timeframe"] == "1h"


def test_learn_bias_slash_command_defaults(telegram_module):
    """'/learn bias ETH' defaults direction=LONG, timeframe=1h."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/learn bias ETH"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "LEARN_BIAS"
    payload = json.loads(symbol)
    assert payload["symbol"] == "ETH"
    assert payload["direction"] == "LONG"
    assert payload["timeframe"] == "1h"


def test_learn_report_plain_text(telegram_module):
    """Plain text 'learn report' dispatches LEARN_REPORT."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("learn report")
    assert result is not None
    assert result["action"] == "LEARN_REPORT"


def test_learn_summary_plain_text(telegram_module):
    """Plain text 'learn summary' dispatches LEARN_SUMMARY."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("learn summary")
    assert result is not None
    assert result["action"] == "LEARN_SUMMARY"


def test_learn_bias_plain_text(telegram_module):
    """Plain text 'learn bias SOL SHORT 4h' dispatches LEARN_BIAS."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("learn bias SOL SHORT 4h")
    assert result is not None
    assert result["action"] == "LEARN_BIAS"
    payload = json.loads(result["symbol"])
    assert payload["symbol"] == "SOL"
    assert payload["direction"] == "SHORT"
    assert payload["timeframe"] == "4h"


# ── Phase 4: Outreach Telegram Commands ─────────────────────────


def test_outreach_post_slash_command(telegram_module):
    """'/outreach post general_invite' dispatches OUTREACH_COMPOSE."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/outreach post general_invite"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "OUTREACH_COMPOSE"
    payload = json.loads(symbol)
    assert payload["template"] == "general_invite"


def test_outreach_post_with_symbol(telegram_module):
    """'/outreach post symbol_specific BTC' passes symbol in payload."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/outreach post symbol_specific BTC"}}
        )
    )
    callback.assert_awaited_once()
    _, symbol, action, _ = callback.await_args.args
    assert action == "OUTREACH_COMPOSE"
    payload = json.loads(symbol)
    assert payload["template"] == "symbol_specific"
    assert payload["symbol"] == "BTC"


def test_outreach_stats_slash_command(telegram_module):
    """'/outreach stats' dispatches OUTREACH_STATS."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/outreach stats"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "OUTREACH_STATS"


def test_outreach_templates_slash_command(telegram_module):
    """'/outreach templates' dispatches OUTREACH_TEMPLATES."""
    callback = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=callback,
    )
    bot.send_message = AsyncMock()
    asyncio.run(
        bot._process_update(
            {"message": {"chat": {"id": "12345"}, "text": "/outreach templates"}}
        )
    )
    callback.assert_awaited_once()
    _, _, action, _ = callback.await_args.args
    assert action == "OUTREACH_TEMPLATES"


def test_outreach_post_plain_text(telegram_module):
    """Plain text 'outreach post symbol_specific ETH' dispatches OUTREACH_COMPOSE."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("outreach post symbol_specific ETH")
    assert result is not None
    assert result["action"] == "OUTREACH_COMPOSE"
    payload = json.loads(result["symbol"])
    assert payload["template"] == "symbol_specific"
    assert payload["symbol"] == "ETH"


def test_outreach_stats_plain_text(telegram_module):
    """Plain text 'outreach stats' dispatches OUTREACH_STATS."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("outreach stats")
    assert result is not None
    assert result["action"] == "OUTREACH_STATS"


def test_outreach_templates_plain_text(telegram_module):
    """Plain text 'outreach templates' dispatches OUTREACH_TEMPLATES."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("outreach templates")
    assert result is not None
    assert result["action"] == "OUTREACH_TEMPLATES"


# ── Phase 5: Task Management Slash Commands ─────────────────────────────────


@pytest.mark.asyncio
async def test_slash_task_create(telegram_module):
    """/task create <title> dispatches TASK_CREATE."""
    mock_cb = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=mock_cb,
    )
    bot.send_as = AsyncMock()
    await bot._process_update({"message": {"text": "/task create Build forum expansion", "chat": {"id": 12345}}})
    mock_cb.assert_called_once()
    args = mock_cb.call_args[0]
    assert args[2] == "TASK_CREATE"
    assert "Build forum expansion" in args[1]


@pytest.mark.asyncio
async def test_slash_task_list(telegram_module):
    """/task list dispatches TASK_LIST."""
    mock_cb = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=mock_cb,
    )
    bot.send_as = AsyncMock()
    await bot._process_update({"message": {"text": "/task list", "chat": {"id": 12345}}})
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][2] == "TASK_LIST"


@pytest.mark.asyncio
async def test_slash_task_list_with_agent_filter(telegram_module):
    """/task list SAPPHIRE dispatches TASK_LIST with agent filter."""
    mock_cb = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=mock_cb,
    )
    bot.send_as = AsyncMock()
    await bot._process_update({"message": {"text": "/task list SAPPHIRE", "chat": {"id": 12345}}})
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][2] == "TASK_LIST"
    assert "SAPPHIRE" in args[1] if (args := mock_cb.call_args[0]) else True


@pytest.mark.asyncio
async def test_slash_task_update(telegram_module):
    """/task update TASK-00001 completed dispatches TASK_UPDATE."""
    mock_cb = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=mock_cb,
    )
    bot.send_as = AsyncMock()
    await bot._process_update({"message": {"text": "/task update TASK-00001 completed", "chat": {"id": 12345}}})
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][2] == "TASK_UPDATE"


@pytest.mark.asyncio
async def test_slash_task_report(telegram_module):
    """/task report dispatches TASK_REPORT."""
    mock_cb = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=mock_cb,
    )
    bot.send_as = AsyncMock()
    await bot._process_update({"message": {"text": "/task report", "chat": {"id": 12345}}})
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][2] == "TASK_REPORT"


@pytest.mark.asyncio
async def test_slash_task_summary(telegram_module):
    """/task summary dispatches TASK_SUMMARY."""
    mock_cb = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=mock_cb,
    )
    bot.send_as = AsyncMock()
    await bot._process_update({"message": {"text": "/task summary", "chat": {"id": 12345}}})
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][2] == "TASK_SUMMARY"


@pytest.mark.asyncio
async def test_slash_task_agent(telegram_module):
    """/task agent EMERALD dispatches TASK_AGENT_REPORT."""
    mock_cb = AsyncMock()
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=mock_cb,
    )
    bot.send_as = AsyncMock()
    await bot._process_update({"message": {"text": "/task agent EMERALD", "chat": {"id": 12345}}})
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][2] == "TASK_AGENT_REPORT"


# ── Phase 5: Task Management Plain-Text Commands ────────────────────────────


def test_task_create_plain_text(telegram_module):
    """Plain text 'task create <title>' dispatches TASK_CREATE."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("task create Build the reputation engine")
    assert result is not None
    assert result["action"] == "TASK_CREATE"


def test_task_list_plain_text(telegram_module):
    """Plain text 'task list' dispatches TASK_LIST."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("task list")
    assert result is not None
    assert result["action"] == "TASK_LIST"


def test_task_update_plain_text(telegram_module):
    """Plain text 'task update TASK-00001 completed' dispatches TASK_UPDATE."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("task update TASK-00001 completed")
    assert result is not None
    assert result["action"] == "TASK_UPDATE"


def test_task_report_plain_text(telegram_module):
    """Plain text 'task report' dispatches TASK_REPORT."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("task report")
    assert result is not None
    assert result["action"] == "TASK_REPORT"


def test_task_summary_plain_text(telegram_module):
    """Plain text 'task summary' dispatches TASK_SUMMARY."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("task summary")
    assert result is not None
    assert result["action"] == "TASK_SUMMARY"


def test_task_agent_plain_text(telegram_module):
    """Plain text 'task agent SAPPHIRE' dispatches TASK_AGENT_REPORT."""
    bot = telegram_module.TelegramPlatformBot(
        bot_token="token", chat_id="12345", command_callback=AsyncMock(),
    )
    result = bot._parse_plain_text_command("task agent SAPPHIRE")
    assert result is not None
    assert result["action"] == "TASK_AGENT_REPORT"
