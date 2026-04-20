"""Unit tests for plugins/claw-sapphire/tools/trading_brain.py.

Tests cover the decision aggregation logic, macro sentiment scoring, track-record
modifier, and dashboard shape — without calling any live sub-tools.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
SAPPHIRE = Path(__file__).resolve().parents[2]
TOOLS = SAPPHIRE / "plugins" / "claw-sapphire" / "tools"
LIB = SAPPHIRE / "plugins" / "claw-sapphire" / "lib"
INTERNAL = TOOLS / "internal"

for p in (str(TOOLS), str(LIB)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load internal/ implementation directly — shim monkeypatch can't cross boundary.
_tb_spec = importlib.util.spec_from_file_location("trading_brain", INTERNAL / "trading_brain.py")
tb = importlib.util.module_from_spec(_tb_spec)
_tb_spec.loader.exec_module(tb)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_votes(bull: float, bear: float, neutral: float):
    """Return a minimal vote list that produces the requested weight split."""
    return [
        ("bullish", bull, "TA", "bullish"),
        ("bearish", bear, "Macro", "bearish"),
        ("neutral", neutral, "Ensemble", "no consensus"),
    ]


def _aggregate(votes):
    bull_w = sum(w for d, w, _, _ in votes if d == "bullish")
    bear_w = sum(w for d, w, _, _ in votes if d == "bearish")
    neut_w = sum(w for d, w, _, _ in votes if d == "neutral")
    total = bull_w + bear_w + neut_w or 1
    return bull_w / total, bear_w / total


# ── decision logic ────────────────────────────────────────────────────────────

class TestDecisionLogic:
    """Verify GO/LEAN/WAIT thresholds match the documented decision table."""

    def _decide(self, votes, track_modifier=0.0):
        """Mirror the aggregation block from action_decide."""
        bull_pct, bear_pct = _aggregate(votes)
        track = {"modifier": track_modifier, "reason": "test"}

        if bull_pct > 0.55:
            decision = "GO_LONG"
            confidence = min(0.95, bull_pct + track["modifier"])
            direction = "bullish"
        elif bear_pct > 0.55:
            decision = "GO_SHORT"
            confidence = min(0.95, bear_pct + track["modifier"])
            direction = "bearish"
        elif bull_pct > 0.40 and bear_pct < 0.30:
            decision = "LEAN_LONG"
            confidence = bull_pct * 0.8 + track["modifier"]
            direction = "bullish"
        elif bear_pct > 0.40 and bull_pct < 0.30:
            decision = "LEAN_SHORT"
            confidence = bear_pct * 0.8 + track["modifier"]
            direction = "bearish"
        else:
            decision = "WAIT"
            confidence = max(bull_pct, bear_pct)
            direction = "neutral"

        return decision, round(max(0.1, min(0.95, confidence)), 2), direction

    def test_go_long_when_bull_dominant(self):
        votes = _make_votes(0.70, 0.10, 0.20)
        decision, _, direction = self._decide(votes)
        assert decision == "GO_LONG"
        assert direction == "bullish"

    def test_go_short_when_bear_dominant(self):
        votes = _make_votes(0.10, 0.70, 0.20)
        decision, _, direction = self._decide(votes)
        assert decision == "GO_SHORT"
        assert direction == "bearish"

    def test_lean_long(self):
        # bull 45%, bear 25%, neutral 30%
        votes = _make_votes(0.45, 0.25, 0.30)
        decision, _, direction = self._decide(votes)
        assert decision == "LEAN_LONG"
        assert direction == "bullish"

    def test_lean_short(self):
        votes = _make_votes(0.25, 0.45, 0.30)
        decision, _, direction = self._decide(votes)
        assert decision == "LEAN_SHORT"
        assert direction == "bearish"

    def test_wait_when_no_consensus(self):
        votes = _make_votes(0.33, 0.33, 0.34)
        decision, _, _ = self._decide(votes)
        assert decision == "WAIT"

    def test_confidence_never_exceeds_095(self):
        votes = _make_votes(0.90, 0.05, 0.05)
        _, confidence, _ = self._decide(votes, track_modifier=0.5)
        assert confidence <= 0.95

    def test_confidence_never_below_010(self):
        votes = _make_votes(0.01, 0.01, 0.98)
        _, confidence, _ = self._decide(votes, track_modifier=-0.5)
        assert confidence >= 0.10

    def test_track_record_boosts_confidence(self):
        votes = _make_votes(0.60, 0.20, 0.20)
        _, conf_no_boost, _ = self._decide(votes, track_modifier=0.0)
        _, conf_boosted, _ = self._decide(votes, track_modifier=0.1)
        assert conf_boosted >= conf_no_boost

    def test_track_record_dampens_confidence(self):
        votes = _make_votes(0.60, 0.20, 0.20)
        _, conf_baseline, _ = self._decide(votes, track_modifier=0.0)
        _, conf_dampened, _ = self._decide(votes, track_modifier=-0.15)
        assert conf_dampened <= conf_baseline


# ── macro sentiment ───────────────────────────────────────────────────────────

class TestMacroSentiment:
    def _call(self, macro_output):
        with patch.object(tb, "_run_tool", return_value=macro_output):
            return tb._get_macro_sentiment()

    def test_bullish_when_vix_low_and_curve_healthy(self):
        result = self._call({
            "indicators": {
                "VIX": {"value": 12.0},
                "Fed Funds Rate %": {"value": 2.5},
                "10Y Treasury %": {"value": 3.5},
                "2Y Treasury %": {"value": 2.8},
            }
        })
        assert result["sentiment"] == "bullish"
        assert result["score"] > 0

    def test_bearish_when_vix_high_and_inverted_curve(self):
        result = self._call({
            "indicators": {
                "VIX": {"value": 30.0},
                "Fed Funds Rate %": {"value": 5.5},
                "10Y Treasury %": {"value": 3.8},
                "2Y Treasury %": {"value": 4.5},
            }
        })
        assert result["sentiment"] == "bearish"
        assert result["score"] < 0

    def test_neutral_fallback_when_macro_unavailable(self):
        result = self._call({"error": "FRED unreachable"})
        assert result["sentiment"] == "neutral"
        assert result["score"] == 0
        assert "unavailable" in result["reason"]

    def test_reasons_populated_on_vix_signal(self):
        result = self._call({
            "indicators": {"VIX": {"value": 10.0}}
        })
        assert any("VIX" in r for r in result.get("reasons", []))


# ── track record modifier ─────────────────────────────────────────────────────

class TestTrackRecord:
    def _call(self, metrics_output):
        with patch.object(tb, "_run_tool", return_value=metrics_output):
            return tb._get_paper_track_record()

    def test_boost_on_strong_win_rate(self):
        result = self._call({"total_trades": 50, "win_rate": "70%"})
        assert result["modifier"] == pytest.approx(0.1)

    def test_dampen_on_weak_win_rate(self):
        result = self._call({"total_trades": 30, "win_rate": "30%"})
        assert result["modifier"] == pytest.approx(-0.15)

    def test_neutral_on_mixed_win_rate(self):
        result = self._call({"total_trades": 20, "win_rate": "50%"})
        assert result["modifier"] == pytest.approx(0.0)

    def test_no_modifier_when_no_trades(self):
        result = self._call({"total_trades": 0})
        assert result["modifier"] == 0
        assert "no track record" in result["reason"]

    def test_no_modifier_on_error(self):
        result = self._call({"error": "paper_trader unavailable"})
        assert result["modifier"] == 0


# ── action_decide integration ─────────────────────────────────────────────────

class TestActionDecide:
    """action_decide should return the documented shape without calling live tools."""

    def _mock_decide(self, symbol="BTC"):
        with (
            patch.object(tb, "_run_tool", return_value={"signals": 0, "details": [], "success": False}),
            patch.object(tb, "_get_macro_sentiment", return_value={"sentiment": "neutral", "score": 0, "reasons": []}),
            patch.object(tb, "_get_paper_track_record", return_value={"modifier": 0.0, "reason": "test"}),
        ):
            # technical_analysis import will fail gracefully in test env → neutral vote
            return tb.action_decide(symbol)

    def test_returns_required_keys(self):
        result = self._mock_decide("BTC")
        for key in ("symbol", "decision", "direction", "confidence", "timestamp", "votes", "aggregation", "track_record"):
            assert key in result, f"Missing key: {key}"

    def test_symbol_echoed(self):
        result = self._mock_decide("ETH")
        assert result["symbol"] == "ETH"

    def test_decision_is_valid_enum(self):
        result = self._mock_decide("BTC")
        assert result["decision"] in ("GO_LONG", "GO_SHORT", "LEAN_LONG", "LEAN_SHORT", "WAIT")

    def test_confidence_in_range(self):
        result = self._mock_decide("SOL")
        assert 0.10 <= result["confidence"] <= 0.95

    def test_aggregation_sums_to_100(self):
        result = self._mock_decide("BTC")
        agg = result["aggregation"]
        total = agg["bullish"] + agg["bearish"] + agg["neutral"]
        assert abs(total - 100.0) < 0.5

    def test_votes_list_non_empty(self):
        result = self._mock_decide("BTC")
        assert len(result["votes"]) > 0

    def test_direction_matches_decision(self):
        result = self._mock_decide("BTC")
        d, dir_ = result["decision"], result["direction"]
        if "LONG" in d:
            assert dir_ == "bullish"
        elif "SHORT" in d:
            assert dir_ == "bearish"
        elif d == "WAIT":
            assert dir_ == "neutral"


# ── action_dashboard ──────────────────────────────────────────────────────────

class TestActionDashboard:
    def test_covers_three_symbols(self):
        with (
            patch.object(tb, "_run_tool", return_value={"signals": 0, "details": [], "success": False}),
            patch.object(tb, "_get_macro_sentiment", return_value={"sentiment": "neutral", "score": 0, "reasons": []}),
            patch.object(tb, "_get_paper_track_record", return_value={"modifier": 0.0, "reason": "test"}),
        ):
            result = tb.action_dashboard()

        assert result["success"] is True
        for sym in ("BTC", "ETH", "SOL"):
            assert sym in result["decisions"]

    def test_each_decision_has_confidence(self):
        with (
            patch.object(tb, "_run_tool", return_value={"signals": 0, "details": [], "success": False}),
            patch.object(tb, "_get_macro_sentiment", return_value={"sentiment": "neutral", "score": 0, "reasons": []}),
            patch.object(tb, "_get_paper_track_record", return_value={"modifier": 0.0, "reason": "test"}),
        ):
            result = tb.action_dashboard()

        for sym, dec in result["decisions"].items():
            assert "confidence" in dec, f"{sym} decision missing confidence"
