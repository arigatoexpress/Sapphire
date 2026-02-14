"""Tests for Phase 4 Bot Reputation & Points System."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

import pytest
from src.collaboration.reputation import BotReputationService


@pytest.fixture
def rep():
    """Fresh reputation service with temp store."""
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["SAPPHIRE_REPUTATION_STORE_PATH"] = tmp
    svc = BotReputationService(store_path=tmp)
    return svc


# ── Basic Registration & Lookup ───────────────────────────────


def test_get_unknown_bot(rep):
    result = rep.get_reputation("UNKNOWN_BOT")
    assert result["ok"] is False
    assert result["error"] == "bot_not_found"


def test_record_idea_creates_bot(rep):
    result = rep.record_idea("BOT_ALPHA")
    assert result["ok"] is True
    assert result["ideas_submitted"] == 1
    assert result["score"] > 0


def test_get_reputation_after_record(rep):
    rep.record_idea("BOT_ALPHA")
    result = rep.get_reputation("BOT_ALPHA")
    assert result["ok"] is True
    assert result["bot_id"] == "BOT_ALPHA"
    assert result["ideas_submitted"] == 1
    assert result["status"] == "active"


def test_case_insensitive_bot_id(rep):
    rep.record_idea("bot_alpha")
    result = rep.get_reputation("BOT_ALPHA")
    assert result["ok"] is True


# ── Idea Outcomes ─────────────────────────────────────────────


def test_record_accurate_profitable_outcome(rep):
    rep.record_idea("BOT_A")
    result = rep.record_outcome("BOT_A", accurate=True, profitable=True, pnl=50.0)
    assert result["ok"] is True
    bot = rep.get_reputation("BOT_A")
    assert bot["ideas_accurate"] == 1
    assert bot["ideas_profitable"] == 1
    assert bot["total_pnl"] == 50.0


def test_record_inaccurate_unprofitable_outcome(rep):
    rep.record_idea("BOT_B")
    result = rep.record_outcome("BOT_B", accurate=False, profitable=False, pnl=-30.0)
    assert result["ok"] is True
    bot = rep.get_reputation("BOT_B")
    assert bot["ideas_inaccurate"] == 1
    assert bot["ideas_unprofitable"] == 1
    assert bot["total_pnl"] == -30.0


def test_score_increases_with_good_outcomes(rep):
    rep.record_idea("BOT_GOOD")
    initial = rep.get_reputation("BOT_GOOD")["score"]
    rep.record_outcome("BOT_GOOD", accurate=True, profitable=True, pnl=100.0)
    after = rep.get_reputation("BOT_GOOD")["score"]
    assert after > initial


def test_score_decreases_with_bad_outcomes(rep):
    rep.record_idea("BOT_BAD")
    initial = rep.get_reputation("BOT_BAD")["score"]
    rep.record_outcome("BOT_BAD", accurate=False, profitable=False, pnl=-100.0)
    after = rep.get_reputation("BOT_BAD")["score"]
    assert after < initial


# ── Quality Ratings ───────────────────────────────────────────


def test_high_quality_adds_bonus(rep):
    rep.record_idea("BOT_Q")
    initial = rep.get_reputation("BOT_Q")["score"]
    rep.record_quality("BOT_Q", 0.9)
    after = rep.get_reputation("BOT_Q")["score"]
    assert after > initial


def test_low_quality_adds_penalty(rep):
    rep.record_idea("BOT_Q")
    initial = rep.get_reputation("BOT_Q")["score"]
    rep.record_quality("BOT_Q", 0.1)
    after = rep.get_reputation("BOT_Q")["score"]
    assert after < initial


def test_quality_average(rep):
    rep.record_idea("BOT_Q")
    rep.record_quality("BOT_Q", 0.8)
    rep.record_quality("BOT_Q", 0.4)
    result = rep.get_reputation("BOT_Q")
    assert abs(result["quality_avg"] - 0.6) < 0.01


def test_quality_clamped(rep):
    rep.record_idea("BOT_Q")
    rep.record_quality("BOT_Q", 5.0)  # Over 1.0
    rep.record_quality("BOT_Q", -2.0)  # Under 0.0
    result = rep.get_reputation("BOT_Q")
    # Should clamp to 1.0 and 0.0
    assert abs(result["quality_avg"] - 0.5) < 0.01  # (1.0 + 0.0) / 2


# ── Penalties & Bans ──────────────────────────────────────────


def test_penalize_bot(rep):
    rep.record_idea("BOT_P")
    result = rep.penalize("BOT_P", "spam detected")
    assert result["ok"] is True
    bot = rep.get_reputation("BOT_P")
    assert bot["penalties"] == 1


def test_five_penalties_warns_bot(rep):
    rep.record_idea("BOT_W")
    for i in range(5):
        rep.penalize("BOT_W", f"warning {i}", points=-2.0)
    bot = rep.get_reputation("BOT_W")
    assert bot["status"] == "warned"


def test_ban_bot(rep):
    result = rep.ban("BOT_EVIL", "malicious injection attempt")
    assert result["ok"] is True
    assert result["status"] == "banned"
    assert rep.is_banned("BOT_EVIL")


def test_banned_bot_cannot_submit_ideas(rep):
    rep.ban("BOT_EVIL", "malicious")
    result = rep.record_idea("BOT_EVIL")
    assert result["ok"] is False
    assert result["error"] == "bot_is_banned"


def test_auto_ban_on_low_score(rep):
    rep.record_idea("BOT_AUTO")
    # Drive score below threshold with heavy penalties
    for _ in range(10):
        rep.record_outcome("BOT_AUTO", accurate=False, profitable=False, pnl=-100.0)
    bot = rep.get_reputation("BOT_AUTO")
    assert bot["status"] == "banned"


def test_is_banned_unknown_bot(rep):
    assert rep.is_banned("NONEXISTENT") is False


# ── Leaderboard ───────────────────────────────────────────────


def test_leaderboard_empty(rep):
    board = rep.leaderboard()
    assert board == []


def test_leaderboard_sorted_by_composite(rep):
    # Bot A: 5 accurate, profitable ideas
    for _ in range(5):
        rep.record_idea("BOT_A")
        rep.record_outcome("BOT_A", accurate=True, profitable=True, pnl=50.0)
    # Bot B: 1 inaccurate, unprofitable idea
    rep.record_idea("BOT_B")
    rep.record_outcome("BOT_B", accurate=False, profitable=False, pnl=-50.0)
    board = rep.leaderboard()
    assert len(board) == 2
    assert board[0]["bot_id"] == "BOT_A"
    assert board[0]["composite"] > board[1]["composite"]


def test_leaderboard_excludes_banned(rep):
    rep.record_idea("BOT_GOOD")
    rep.ban("BOT_BAD", "banned")
    board = rep.leaderboard()
    assert len(board) == 1
    assert board[0]["bot_id"] == "BOT_GOOD"


def test_leaderboard_limit(rep):
    for i in range(25):
        rep.record_idea(f"BOT_{i:03d}")
    board = rep.leaderboard(limit=10)
    assert len(board) == 10


# ── Reputation Weight ─────────────────────────────────────────


def test_reputation_weight_unknown(rep):
    weight = rep.reputation_weight("UNKNOWN")
    assert weight == 0.1  # Minimal weight


def test_reputation_weight_banned(rep):
    rep.ban("BOT_EVIL", "malicious")
    weight = rep.reputation_weight("BOT_EVIL")
    assert weight == 0.0


def test_reputation_weight_active(rep):
    for _ in range(3):
        rep.record_idea("BOT_ACTIVE")
        rep.record_outcome("BOT_ACTIVE", accurate=True, profitable=True, pnl=20.0)
    weight = rep.reputation_weight("BOT_ACTIVE")
    assert 0.0 < weight <= 1.0


def test_reputation_weight_range(rep):
    rep.record_idea("BOT_TEST")
    weight = rep.reputation_weight("BOT_TEST")
    assert 0.05 <= weight <= 1.0


# ── Bot Count ─────────────────────────────────────────────────


def test_bot_count_empty(rep):
    counts = rep.bot_count()
    assert counts == {"active": 0, "warned": 0, "banned": 0}


def test_bot_count_mixed(rep):
    rep.record_idea("BOT_ACTIVE")
    rep.ban("BOT_BANNED", "test")
    counts = rep.bot_count()
    assert counts["active"] == 1
    assert counts["banned"] == 1


# ── History Tracking ──────────────────────────────────────────


def test_history_records_actions(rep):
    rep.record_idea("BOT_H")
    rep.record_outcome("BOT_H", accurate=True, profitable=True, pnl=10.0)
    bot = rep._bots["BOT_H"]
    assert len(bot["history"]) == 3  # idea_submitted + accurate + profitable


def test_history_max_50(rep):
    rep.record_idea("BOT_H")
    for _ in range(60):
        rep.record_quality("BOT_H", 0.8)
    bot = rep._bots["BOT_H"]
    assert len(bot["history"]) <= 50
