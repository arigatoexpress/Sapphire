"""Tests for Phase 4 Swarm Intelligence — Reputation-Weighted Aggregation."""

import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

import pytest
from src.collaboration.reputation import BotReputationService
from src.collaboration.swarm import SwarmAggregator


@pytest.fixture
def swarm():
    """Fresh swarm aggregator with temp reputation store."""
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["SAPPHIRE_REPUTATION_STORE_PATH"] = tmp
    rep = BotReputationService(store_path=tmp)
    return SwarmAggregator(reputation=rep)


@pytest.fixture
def rep_and_swarm():
    """Expose both reputation and swarm for advanced tests."""
    tmp = tempfile.mktemp(suffix=".json")
    rep = BotReputationService(store_path=tmp)
    return rep, SwarmAggregator(reputation=rep)


# ── Basic Idea Submission ────────────────────────────────────────


def test_submit_idea_success(swarm):
    result = swarm.submit_idea("BOT_A", "BTC/USDT", "LONG", confidence=0.8)
    assert result["ok"] is True
    assert result["idea_id"].startswith("IDEA-")
    assert result["symbol"] == "BTC/USDT"
    assert result["direction"] == "LONG"
    assert result["confidence"] == 0.8
    assert result["reputation_weight"] > 0


def test_submit_idea_short(swarm):
    result = swarm.submit_idea("BOT_A", "ETH", "SHORT", confidence=0.6)
    assert result["ok"] is True
    assert result["direction"] == "SHORT"


def test_submit_invalid_direction(swarm):
    result = swarm.submit_idea("BOT_A", "BTC", "SIDEWAYS")
    assert result["ok"] is False
    assert result["error"] == "invalid_direction"


def test_submit_missing_symbol(swarm):
    result = swarm.submit_idea("BOT_A", "", "LONG")
    assert result["ok"] is False
    assert result["error"] == "missing_symbol"


def test_submit_banned_bot(rep_and_swarm):
    rep, swarm = rep_and_swarm
    rep.ban("BOT_EVIL", "malicious")
    result = swarm.submit_idea("BOT_EVIL", "BTC", "LONG")
    assert result["ok"] is False
    assert result["error"] == "bot_is_banned"


def test_submit_confidence_clamped(swarm):
    result = swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=5.0)
    assert result["confidence"] == 1.0
    result2 = swarm.submit_idea("BOT_B", "BTC", "LONG", confidence=-1.0)
    assert result2["confidence"] == 0.0


def test_submit_increments_idea_count(rep_and_swarm):
    rep, swarm = rep_and_swarm
    swarm.submit_idea("BOT_A", "BTC", "LONG")
    swarm.submit_idea("BOT_A", "BTC", "LONG")
    bot = rep.get_reputation("BOT_A")
    assert bot["ideas_submitted"] == 2


# ── Aggregation ──────────────────────────────────────────────────


def test_aggregate_empty_symbol(swarm):
    result = swarm.aggregate("BTC")
    assert result["ok"] is True
    assert result["consensus"] == "NEUTRAL"
    assert result["total_ideas"] == 0
    assert result["conviction"] == 0.0


def test_aggregate_single_long(swarm):
    swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.9)
    result = swarm.aggregate("BTC")
    assert result["ok"] is True
    assert result["consensus"] in ("LONG", "LEAN_LONG")
    assert result["total_ideas"] == 1
    assert result["long_count"] == 1
    assert result["short_count"] == 0
    assert result["weighted_long"] > 0
    assert result["weighted_short"] == 0


def test_aggregate_single_short(swarm):
    swarm.submit_idea("BOT_A", "ETH", "SHORT", confidence=0.9)
    result = swarm.aggregate("ETH")
    assert result["consensus"] in ("SHORT", "LEAN_SHORT")
    assert result["short_count"] == 1


def test_aggregate_strong_consensus_long(swarm):
    """Multiple bots agree on LONG → high conviction."""
    for i in range(5):
        swarm.submit_idea(f"BOT_{i}", "BTC", "LONG", confidence=0.8)
    result = swarm.aggregate("BTC")
    assert result["consensus"] == "LONG"
    assert result["conviction"] >= 0.99  # All same direction
    assert result["long_count"] == 5


def test_aggregate_strong_consensus_short(swarm):
    """Multiple bots agree on SHORT."""
    for i in range(4):
        swarm.submit_idea(f"BOT_{i}", "SOL", "SHORT", confidence=0.7)
    result = swarm.aggregate("SOL")
    assert result["consensus"] == "SHORT"
    assert result["conviction"] >= 0.99


def test_aggregate_split_opinion_neutral(swarm):
    """Equal long and short with same weights → neutral."""
    swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.5)
    swarm.submit_idea("BOT_B", "BTC", "SHORT", confidence=0.5)
    result = swarm.aggregate("BTC")
    # Both bots are new with same default rep, so conviction should be ~0.5
    assert result["conviction"] == pytest.approx(0.5, abs=0.05)
    assert result["consensus"] in ("NEUTRAL", "LEAN_LONG", "LEAN_SHORT")


def test_aggregate_reputation_weighting(rep_and_swarm):
    """A high-reputation bot's idea should outweigh a low-reputation one."""
    rep, swarm = rep_and_swarm
    # Build reputation for BOT_GOOD
    for _ in range(5):
        rep.record_idea("BOT_GOOD")
        rep.record_outcome("BOT_GOOD", accurate=True, profitable=True, pnl=50.0)

    # BOT_BAD stays at default
    swarm.submit_idea("BOT_GOOD", "BTC", "LONG", confidence=0.8)
    swarm.submit_idea("BOT_BAD", "BTC", "SHORT", confidence=0.8)

    result = swarm.aggregate("BTC")
    # BOT_GOOD has higher weight, so LONG should dominate
    assert result["weighted_long"] > result["weighted_short"]
    assert result["consensus"] in ("LONG", "LEAN_LONG")


def test_aggregate_net_score(swarm):
    """Net score = weighted_long - weighted_short."""
    swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.9)
    swarm.submit_idea("BOT_B", "BTC", "SHORT", confidence=0.3)
    result = swarm.aggregate("BTC")
    expected_net = result["weighted_long"] - result["weighted_short"]
    assert abs(result["net_score"] - expected_net) < 0.01


def test_aggregate_missing_symbol(swarm):
    result = swarm.aggregate("")
    assert result["ok"] is False
    assert result["error"] == "missing_symbol"


def test_aggregate_contributors_list(swarm):
    swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.7)
    swarm.submit_idea("BOT_B", "BTC", "SHORT", confidence=0.5)
    result = swarm.aggregate("BTC")
    assert len(result["contributors"]) == 2
    bot_ids = {c["bot_id"] for c in result["contributors"]}
    assert "BOT_A" in bot_ids
    assert "BOT_B" in bot_ids


# ── Idea Lifecycle ───────────────────────────────────────────────


def test_get_idea(swarm):
    result = swarm.submit_idea("BOT_A", "BTC", "LONG")
    idea_id = result["idea_id"]
    idea = swarm.get_idea(idea_id)
    assert idea is not None
    assert idea["bot_id"] == "BOT_A"
    assert idea["direction"] == "LONG"
    assert idea["status"] == "open"


def test_get_idea_not_found(swarm):
    assert swarm.get_idea("IDEA-99999") is None


def test_record_outcome_success(rep_and_swarm):
    rep, swarm = rep_and_swarm
    submit = swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.8)
    idea_id = submit["idea_id"]
    outcome = swarm.record_idea_outcome(idea_id, accurate=True, profitable=True, pnl=100.0)
    assert outcome["ok"] is True
    assert outcome["idea_id"] == idea_id
    assert outcome["accurate"] is True
    assert outcome["profitable"] is True
    assert outcome["pnl"] == 100.0
    # Idea should be resolved
    idea = swarm.get_idea(idea_id)
    assert idea["status"] == "resolved"


def test_record_outcome_not_found(swarm):
    result = swarm.record_idea_outcome("IDEA-99999", accurate=True, profitable=True)
    assert result["ok"] is False
    assert result["error"] == "idea_not_found"


def test_record_outcome_updates_reputation(rep_and_swarm):
    rep, swarm = rep_and_swarm
    submit = swarm.submit_idea("BOT_TRACKED", "ETH", "SHORT")
    swarm.record_idea_outcome(submit["idea_id"], accurate=True, profitable=True, pnl=50.0)
    bot = rep.get_reputation("BOT_TRACKED")
    assert bot["ideas_accurate"] == 1
    assert bot["ideas_profitable"] == 1
    assert bot["total_pnl"] == 50.0


# ── Open Ideas & Active Symbols ──────────────────────────────────


def test_open_ideas_by_symbol(swarm):
    swarm.submit_idea("BOT_A", "BTC", "LONG")
    swarm.submit_idea("BOT_B", "ETH", "SHORT")
    btc_ideas = swarm.open_ideas("BTC")
    assert len(btc_ideas) == 1
    assert btc_ideas[0]["symbol"] == "BTC"


def test_open_ideas_all(swarm):
    swarm.submit_idea("BOT_A", "BTC", "LONG")
    swarm.submit_idea("BOT_B", "ETH", "SHORT")
    all_ideas = swarm.open_ideas()
    assert len(all_ideas) == 2


def test_active_symbols(swarm):
    swarm.submit_idea("BOT_A", "BTC", "LONG")
    swarm.submit_idea("BOT_B", "ETH", "SHORT")
    swarm.submit_idea("BOT_C", "SOL", "LONG")
    symbols = swarm.active_symbols()
    assert sorted(symbols) == ["BTC", "ETH", "SOL"]


def test_resolved_ideas_not_in_open(swarm):
    submit = swarm.submit_idea("BOT_A", "BTC", "LONG")
    swarm.record_idea_outcome(submit["idea_id"], accurate=True, profitable=True)
    assert len(swarm.open_ideas("BTC")) == 0


# ── Expiry ───────────────────────────────────────────────────────


def test_expired_ideas_excluded_from_aggregate(swarm):
    """Ideas older than TTL should be marked expired and excluded."""
    swarm.submit_idea("BOT_A", "BTC", "LONG")
    # Manually backdate the idea
    for idea in swarm._ideas["BTC"]:
        idea["submitted_at"] = int(time.time()) - swarm.IDEA_TTL_SECONDS - 10
    result = swarm.aggregate("BTC")
    assert result["total_ideas"] == 0
    assert result["consensus"] == "NEUTRAL"


def test_expired_ideas_not_in_open(swarm):
    swarm.submit_idea("BOT_A", "ETH", "SHORT")
    for idea in swarm._ideas["ETH"]:
        idea["submitted_at"] = int(time.time()) - swarm.IDEA_TTL_SECONDS - 10
    assert len(swarm.open_ideas("ETH")) == 0


# ── Stats ────────────────────────────────────────────────────────


def test_stats_empty(swarm):
    stats = swarm.stats()
    assert stats["total_ideas_submitted"] == 0
    assert stats["open_ideas"] == 0
    assert stats["active_symbols"] == 0


def test_stats_after_submissions(swarm):
    swarm.submit_idea("BOT_A", "BTC", "LONG")
    swarm.submit_idea("BOT_B", "ETH", "SHORT")
    submit = swarm.submit_idea("BOT_C", "BTC", "SHORT")
    swarm.record_idea_outcome(submit["idea_id"], accurate=False, profitable=False)
    stats = swarm.stats()
    assert stats["total_ideas_submitted"] == 3
    assert stats["open_ideas"] == 2
    assert stats["resolved_ideas"] == 1
    assert stats["active_symbols"] == 2


# ── Max Ideas Per Symbol ─────────────────────────────────────────


def test_max_ideas_per_symbol(swarm):
    """Oldest idea should be evicted when limit is reached."""
    swarm.MAX_IDEAS_PER_SYMBOL = 5
    for i in range(7):
        swarm.submit_idea(f"BOT_{i}", "BTC", "LONG")
    assert len(swarm._ideas["BTC"]) == 5


# ── Target Price / Stop Loss Aggregation ─────────────────────────


def test_aggregate_target_and_stop(swarm):
    """Average target and stop should be weighted by reputation."""
    swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.8, target_price=50000.0, stop_loss=45000.0)
    swarm.submit_idea("BOT_B", "BTC", "LONG", confidence=0.6, target_price=52000.0, stop_loss=44000.0)
    result = swarm.aggregate("BTC")
    # Both bots same default rep → target/stop should be between the two values
    assert 49000 < result["avg_target_price"] < 53000
    assert 43000 < result["avg_stop_loss"] < 46000


def test_aggregate_target_zero_when_none_provided(swarm):
    swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.8)
    result = swarm.aggregate("BTC")
    assert result["avg_target_price"] == 0.0
    assert result["avg_stop_loss"] == 0.0
