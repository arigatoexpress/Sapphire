import pytest
pytestmark = pytest.mark.skip(reason="Legacy test — depends on removed module")
pytest.skip("Legacy test — depends on removed module", allow_module_level=True)
"""Unit tests for the Agent Activity Feed."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

from shared.telegram_bot import (
    EMERALD,
    OBSIDIAN,
    SAPPHIRE,
    TelegramPlatformBot,
)


def _bot():
    """Create a bot instance with no real Telegram credentials."""
    return TelegramPlatformBot(bot_token="", chat_id="")


# ── record_activity ──────────────────────────────────────────────


def test_record_activity_appends_event():
    bot = _bot()
    bot.record_activity(SAPPHIRE, "trade", "Filled BUY 0.5 SOL")
    assert len(bot._activity_feed) == 1
    evt = bot._activity_feed[0]
    assert evt["agent"] == "Sapphire"
    assert evt["category"] == "trade"
    assert evt["detail"] == "Filled BUY 0.5 SOL"
    assert "ts" in evt


def test_record_activity_disabled():
    bot = _bot()
    bot._activity_feed_enabled = False
    bot.record_activity(SAPPHIRE, "trade", "should not appear")
    assert len(bot._activity_feed) == 0


def test_record_activity_caps_at_max():
    bot = _bot()
    bot._activity_feed_max = 5
    for i in range(10):
        bot.record_activity(OBSIDIAN, "system", f"event-{i}")
    assert len(bot._activity_feed) == 5
    # Should keep the last 5
    assert bot._activity_feed[0]["detail"] == "event-5"
    assert bot._activity_feed[-1]["detail"] == "event-9"


def test_record_activity_truncates_long_detail():
    bot = _bot()
    bot.record_activity(EMERALD, "cognition", "x" * 500)
    assert len(bot._activity_feed[0]["detail"]) == 200


# ── _flush_activity_feed (digest formatting) ─────────────────────


import asyncio


def test_flush_activity_feed_clears_buffer():
    bot = _bot()
    bot.record_activity(SAPPHIRE, "trade", "BUY SOL")
    bot.record_activity(SAPPHIRE, "trade", "BUY ETH")
    # Flush won't dispatch (no credentials) but should clear the buffer
    asyncio.run(bot._flush_activity_feed())
    assert len(bot._activity_feed) == 0


def test_flush_activity_feed_groups_by_agent_and_category():
    bot = _bot()
    bot.record_activity(SAPPHIRE, "trade", "BUY SOL")
    bot.record_activity(SAPPHIRE, "trade", "BUY SOL")
    bot.record_activity(SAPPHIRE, "trade", "BUY ETH")
    bot.record_activity(EMERALD, "cognition", "BUY SOL conf=85%")
    bot.record_activity(OBSIDIAN, "system", "Startup complete")

    # Manually build the grouped data to verify the logic
    from collections import OrderedDict

    events = list(bot._activity_feed)
    groups = OrderedDict()
    for evt in events:
        key = f"{evt['emoji']}:{evt['category']}"
        if key not in groups:
            groups[key] = {
                "emoji": evt["emoji"],
                "agent": evt["agent"],
                "category": evt["category"],
                "details": OrderedDict(),
                "count": 0,
            }
        groups[key]["count"] += 1
        detail = evt["detail"]
        if detail in groups[key]["details"]:
            groups[key]["details"][detail] += 1
        else:
            groups[key]["details"][detail] = 1

    # 3 groups: Sapphire/trade, Emerald/cognition, Obsidian/system
    assert len(groups) == 3
    trade_group = groups["💎:trade"]
    assert trade_group["count"] == 3
    assert trade_group["details"]["BUY SOL"] == 2
    assert trade_group["details"]["BUY ETH"] == 1


def test_flush_activity_feed_noop_when_empty():
    bot = _bot()
    asyncio.run(bot._flush_activity_feed())
    assert len(bot._activity_feed) == 0


# ── Multiple agents ──────────────────────────────────────────────


def test_multiple_agents_recorded():
    bot = _bot()
    bot.record_activity(SAPPHIRE, "trade", "Dispatched BUY SOL → ASTER")
    bot.record_activity(EMERALD, "memory", "Recorded trade: BUY SOL")
    bot.record_activity(OBSIDIAN, "autonomy", "Dispatched cycle: startup_bootstrap")

    agents = {evt["agent"] for evt in bot._activity_feed}
    assert agents == {"Sapphire", "Emerald", "Obsidian"}
    categories = {evt["category"] for evt in bot._activity_feed}
    assert categories == {"trade", "memory", "autonomy"}
