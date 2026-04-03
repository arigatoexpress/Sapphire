"""Tests for Phase 4 Collaborative Learning — Swarm Knowledge Extraction."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha"))

import pytest
from src.collaboration.learning import SwarmLearning


@pytest.fixture
def learning():
    return SwarmLearning()


# ── Basic Recording ──────────────────────────────────────────────


def test_record_outcome_success(learning):
    result = learning.record_outcome(
        symbol="BTC/USDT", direction="LONG", timeframe="1h",
        conviction=0.8, contributors=["BOT_A", "BOT_B"],
        accurate=True, profitable=True, pnl=100.0,
    )
    assert result["ok"] is True
    assert result["total_records"] == 1


def test_record_multiple_outcomes(learning):
    for i in range(10):
        learning.record_outcome(
            symbol="ETH", direction="SHORT", timeframe="4h",
            conviction=0.6, contributors=[f"BOT_{i}"],
            accurate=i % 2 == 0, profitable=i % 3 == 0, pnl=10.0 if i % 3 == 0 else -5.0,
        )
    summary = learning.summary()
    assert summary["total_records"] == 10


def test_record_normalizes_inputs(learning):
    learning.record_outcome(
        symbol="  btc  ", direction="long", timeframe="  1h  ",
        conviction=1.5,  # should clamp to 1.0
        contributors=["bot_a"], accurate=True, profitable=True, pnl=50.0,
    )
    insights = learning.get_symbol_insights(min_samples=1)
    assert insights[0]["symbol"] == "BTC"


def test_history_max_cap(learning):
    learning.MAX_HISTORY = 10
    for i in range(20):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=1.0,
        )
    assert learning.summary()["total_records"] == 10


# ── Symbol Insights ──────────────────────────────────────────────


def test_symbol_insights_empty(learning):
    insights = learning.get_symbol_insights()
    assert insights == []


def test_symbol_insights_with_data(learning):
    for _ in range(6):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.7, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=50.0,
        )
    for _ in range(4):
        learning.record_outcome(
            symbol="BTC", direction="SHORT", timeframe="1h",
            conviction=0.5, contributors=["BOT_B"],
            accurate=False, profitable=False, pnl=-20.0,
        )
    insights = learning.get_symbol_insights(min_samples=1)
    assert len(insights) == 1
    btc = insights[0]
    assert btc["symbol"] == "BTC"
    assert btc["count"] == 10
    assert btc["wins"] == 6
    assert btc["losses"] == 4
    assert btc["win_rate"] == 0.6
    assert btc["total_pnl"] == 220.0  # 6*50 + 4*(-20)
    assert btc["edge"] == "positive"


def test_symbol_insights_min_samples_filter(learning):
    for _ in range(3):
        learning.record_outcome(
            symbol="SOL", direction="LONG", timeframe="1h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=10.0,
        )
    # Default MIN_SAMPLES_FOR_INSIGHT is 5
    insights = learning.get_symbol_insights()
    assert len(insights) == 0  # Not enough samples
    insights_low = learning.get_symbol_insights(min_samples=2)
    assert len(insights_low) == 1


# ── Timeframe Insights ───────────────────────────────────────────


def test_timeframe_insights(learning):
    for _ in range(5):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.7, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=30.0,
        )
    for _ in range(5):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="4h",
            conviction=0.7, contributors=["BOT_A"],
            accurate=True, profitable=False, pnl=-10.0,
        )
    insights = learning.get_timeframe_insights()
    assert len(insights) == 2
    # 1h should have higher win rate
    tf_1h = next(i for i in insights if i["timeframe"] == "1h")
    tf_4h = next(i for i in insights if i["timeframe"] == "4h")
    assert tf_1h["win_rate"] == 1.0
    assert tf_4h["win_rate"] == 0.0
    assert tf_1h["accuracy"] == 1.0
    assert tf_4h["accuracy"] == 1.0


# ── Direction Insights ───────────────────────────────────────────


def test_direction_insights_empty(learning):
    result = learning.get_direction_insights()
    assert result["LONG"]["count"] == 0
    assert result["SHORT"]["count"] == 0


def test_direction_insights_with_data(learning):
    for _ in range(8):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.7, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=20.0,
        )
    for _ in range(2):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.3, contributors=["BOT_A"],
            accurate=False, profitable=False, pnl=-10.0,
        )
    result = learning.get_direction_insights()
    assert result["LONG"]["count"] == 10
    assert result["LONG"]["win_rate"] == 0.8
    assert result["SHORT"]["count"] == 0


# ── Conviction Calibration ───────────────────────────────────────


def test_conviction_calibration(learning):
    # High conviction → mostly wins
    for _ in range(5):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.9, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=50.0,
        )
    # Low conviction → mostly losses
    for _ in range(5):
        learning.record_outcome(
            symbol="ETH", direction="SHORT", timeframe="4h",
            conviction=0.2, contributors=["BOT_B"],
            accurate=False, profitable=False, pnl=-20.0,
        )
    cal = learning.get_conviction_calibration()
    assert len(cal) == 2
    high = next(c for c in cal if c["conviction_range"] == "85-100%")
    low = next(c for c in cal if c["conviction_range"] == "0-25%")
    assert high["actual_win_rate"] == 1.0
    assert low["actual_win_rate"] == 0.0


def test_conviction_bucket_mapping(learning):
    assert learning._conviction_bucket(0.1) == "0-25%"
    assert learning._conviction_bucket(0.3) == "25-50%"
    assert learning._conviction_bucket(0.6) == "50-70%"
    assert learning._conviction_bucket(0.75) == "70-85%"
    assert learning._conviction_bucket(0.95) == "85-100%"


# ── Bot Synergy ──────────────────────────────────────────────────


def test_bot_synergy_empty(learning):
    assert learning.get_bot_synergy() == []


def test_bot_synergy_with_pairs(learning):
    # BOT_A + BOT_B always win together
    for _ in range(5):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.8, contributors=["BOT_A", "BOT_B"],
            accurate=True, profitable=True, pnl=40.0,
        )
    # BOT_C + BOT_D always lose together
    for _ in range(5):
        learning.record_outcome(
            symbol="ETH", direction="SHORT", timeframe="4h",
            conviction=0.5, contributors=["BOT_C", "BOT_D"],
            accurate=False, profitable=False, pnl=-15.0,
        )
    synergy = learning.get_bot_synergy()
    assert len(synergy) == 2
    good_pair = next(s for s in synergy if s["pair"] == "BOT_A+BOT_B")
    bad_pair = next(s for s in synergy if s["pair"] == "BOT_C+BOT_D")
    assert good_pair["win_rate"] == 1.0
    assert good_pair["synergy"] == "strong"
    assert bad_pair["win_rate"] == 0.0
    assert bad_pair["synergy"] == "weak"


def test_bot_synergy_three_contributors(learning):
    """Three contributors should produce three pair entries."""
    for _ in range(5):
        learning.record_outcome(
            symbol="SOL", direction="LONG", timeframe="1h",
            conviction=0.7, contributors=["BOT_A", "BOT_B", "BOT_C"],
            accurate=True, profitable=True, pnl=10.0,
        )
    synergy = learning.get_bot_synergy()
    pair_keys = {s["pair"] for s in synergy}
    assert "BOT_A+BOT_B" in pair_keys
    assert "BOT_A+BOT_C" in pair_keys
    assert "BOT_B+BOT_C" in pair_keys


# ── Bias Adjustments ─────────────────────────────────────────────


def test_symbol_bias_insufficient_data(learning):
    learning.record_outcome(
        symbol="BTC", direction="LONG", timeframe="1h",
        conviction=0.5, contributors=["BOT_A"],
        accurate=True, profitable=True, pnl=10.0,
    )
    assert learning.get_symbol_bias("BTC") == 0.0  # Not enough samples


def test_symbol_bias_positive(learning):
    for _ in range(10):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.7, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=50.0,
        )
    bias = learning.get_symbol_bias("BTC")
    assert bias == 1.0  # 100% win rate → max positive bias


def test_symbol_bias_negative(learning):
    for _ in range(10):
        learning.record_outcome(
            symbol="DOGE", direction="LONG", timeframe="1h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=False, profitable=False, pnl=-10.0,
        )
    bias = learning.get_symbol_bias("DOGE")
    assert bias == -1.0  # 0% win rate → max negative bias


def test_symbol_bias_neutral(learning):
    for i in range(10):
        learning.record_outcome(
            symbol="ETH", direction="LONG", timeframe="1h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=True, profitable=i < 5, pnl=10.0 if i < 5 else -10.0,
        )
    bias = learning.get_symbol_bias("ETH")
    assert bias == 0.0  # 50% win rate → neutral


def test_timeframe_bias(learning):
    for _ in range(8):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=10.0,
        )
    for _ in range(2):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=False, profitable=False, pnl=-5.0,
        )
    bias = learning.get_timeframe_bias("1h")
    assert bias > 0  # 80% win rate → positive bias


def test_direction_bias(learning):
    for _ in range(6):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=10.0,
        )
    bias = learning.get_direction_bias("LONG")
    assert bias == 1.0  # All wins


# ── Adaptive Confidence ──────────────────────────────────────────


def test_adaptive_confidence_no_data(learning):
    """With no history, should return raw confidence unchanged."""
    adjusted = learning.adaptive_confidence("BTC", "LONG", "1h", 0.7)
    assert adjusted == 0.7


def test_adaptive_confidence_positive_bias(learning):
    """With strong positive history, should increase confidence."""
    for _ in range(10):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.8, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=50.0,
        )
    adjusted = learning.adaptive_confidence("BTC", "LONG", "1h", 0.6)
    assert adjusted > 0.6  # Should be boosted


def test_adaptive_confidence_negative_bias(learning):
    """With strong negative history, should decrease confidence."""
    for _ in range(10):
        learning.record_outcome(
            symbol="DOGE", direction="SHORT", timeframe="4h",
            conviction=0.5, contributors=["BOT_A"],
            accurate=False, profitable=False, pnl=-20.0,
        )
    adjusted = learning.adaptive_confidence("DOGE", "SHORT", "4h", 0.6)
    assert adjusted < 0.6  # Should be reduced


def test_adaptive_confidence_clamped(learning):
    """Adjusted confidence should be clamped 0.0–1.0."""
    for _ in range(10):
        learning.record_outcome(
            symbol="BTC", direction="LONG", timeframe="1h",
            conviction=0.9, contributors=["BOT_A"],
            accurate=True, profitable=True, pnl=100.0,
        )
    adjusted = learning.adaptive_confidence("BTC", "LONG", "1h", 0.99)
    assert 0.0 <= adjusted <= 1.0


# ── Report Generation ────────────────────────────────────────────


def test_generate_report_empty(learning):
    report = learning.generate_report()
    assert report["ok"] is True
    assert report["total_records"] == 0
    assert "message" in report


def test_generate_report_with_data(learning):
    for i in range(10):
        learning.record_outcome(
            symbol="BTC" if i < 7 else "ETH",
            direction="LONG" if i < 6 else "SHORT",
            timeframe="1h" if i < 5 else "4h",
            conviction=0.3 + (i * 0.07),
            contributors=["BOT_A", "BOT_B"] if i < 5 else ["BOT_C"],
            accurate=i < 7,
            profitable=i < 6,
            pnl=20.0 if i < 6 else -10.0,
        )
    report = learning.generate_report()
    assert report["ok"] is True
    assert report["total_records"] == 10
    assert "overall" in report
    assert "symbols" in report
    assert "timeframes" in report
    assert "directions" in report
    assert "conviction_calibration" in report
    assert "bot_synergy" in report
    assert report["overall"]["wins"] == 6
    assert report["overall"]["losses"] == 4


# ── Summary ──────────────────────────────────────────────────────


def test_summary_empty(learning):
    s = learning.summary()
    assert s["total_records"] == 0
    assert s["symbols_tracked"] == 0


def test_summary_with_data(learning):
    learning.record_outcome(
        symbol="BTC", direction="LONG", timeframe="1h",
        conviction=0.7, contributors=["BOT_A"],
        accurate=True, profitable=True, pnl=50.0,
    )
    learning.record_outcome(
        symbol="ETH", direction="SHORT", timeframe="4h",
        conviction=0.5, contributors=["BOT_B"],
        accurate=False, profitable=False, pnl=-20.0,
    )
    s = learning.summary()
    assert s["total_records"] == 2
    assert s["symbols_tracked"] == 2
    assert s["timeframes_tracked"] == 2
    assert s["total_pnl"] == 30.0
    assert s["overall_win_rate"] == 0.5
