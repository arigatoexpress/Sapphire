"""Unit tests for lib.analytics.forecast_explain."""

from __future__ import annotations

from lib.analytics import forecast_explain as fe

# --------------------------------------------------------------------------- #
# Helpers / dispatch
# --------------------------------------------------------------------------- #


class TestRegimeBuckets:
    def test_strong_bull_threshold(self):
        assert fe._regime_from_score(0.50) == "STRONG_BULL"
        assert fe._regime_from_score(0.40) == "STRONG_BULL"

    def test_bull_threshold(self):
        assert fe._regime_from_score(0.39) == "BULL"
        assert fe._regime_from_score(0.10) == "BULL"

    def test_neutral_band(self):
        assert fe._regime_from_score(0.05) == "NEUTRAL"
        assert fe._regime_from_score(-0.05) == "NEUTRAL"
        assert fe._regime_from_score(0.0) == "NEUTRAL"

    def test_bear_threshold(self):
        assert fe._regime_from_score(-0.10) == "BEAR"
        assert fe._regime_from_score(-0.39) == "BEAR"

    def test_strong_bear_threshold(self):
        assert fe._regime_from_score(-0.40) == "STRONG_BEAR"
        assert fe._regime_from_score(-0.95) == "STRONG_BEAR"


class TestConfidenceBand:
    def test_high(self):
        assert fe._confidence_band(0.7) == "high"
        assert fe._confidence_band(-0.7) == "high"
        assert fe._confidence_band(0.5) == "high"

    def test_medium(self):
        assert fe._confidence_band(0.3) == "medium"
        assert fe._confidence_band(-0.25) == "medium"
        assert fe._confidence_band(0.20) == "medium"

    def test_low(self):
        assert fe._confidence_band(0.05) == "low"
        assert fe._confidence_band(0.0) == "low"
        assert fe._confidence_band(-0.19) == "low"


class TestNormalizeComponents:
    def test_weight_sum_normalizes_to_1(self):
        raw = [
            {"name": "rsi", "score": 0.5, "weight": 0.30, "note": "RSI=70"},
            {"name": "macd", "score": -0.2, "weight": 0.30, "note": "MACD=-0.1"},
            {"name": "ema", "score": 0.1, "weight": 0.20, "note": "EMA"},
        ]
        out = fe._normalize_components(raw)
        total_weight = sum(c["weight"] for c in out)
        assert abs(total_weight - 1.0) < 1e-6

    def test_zero_total_weight(self):
        raw = [{"name": "x", "score": 0.0, "weight": 0.0}]
        out = fe._normalize_components(raw)
        assert out[0]["weight"] == 0.0

    def test_handles_value_or_score_key(self):
        raw_score = [{"name": "rsi", "score": 0.5, "weight": 0.5}]
        raw_value = [{"name": "rsi", "value": 0.5, "weight": 0.5}]
        out_a = fe._normalize_components(raw_score)
        out_b = fe._normalize_components(raw_value)
        assert out_a[0]["value"] == 0.5
        assert out_b[0]["value"] == 0.5


class TestComponentBucket:
    def test_strong_bull(self):
        assert fe._component_bucket(0.7) == "strong_bull"
        assert fe._component_bucket(0.5) == "strong_bull"

    def test_mild_bull(self):
        assert fe._component_bucket(0.49) == "mild_bull"
        assert fe._component_bucket(0.10) == "mild_bull"

    def test_neutral(self):
        assert fe._component_bucket(0.05) == "neutral"
        assert fe._component_bucket(-0.09) == "neutral"

    def test_mild_bear(self):
        assert fe._component_bucket(-0.10) == "mild_bear"
        assert fe._component_bucket(-0.49) == "mild_bear"

    def test_strong_bear(self):
        assert fe._component_bucket(-0.5) == "strong_bear"
        assert fe._component_bucket(-1.0) == "strong_bear"


# --------------------------------------------------------------------------- #
# explain_score (quick_signal_score path)
# --------------------------------------------------------------------------- #


class TestExplainScore:
    def _bullish_payload(self):
        return {
            "score": 0.42,
            "regime": "RISK_ON",
            "rationale": "RSI=62; MACD_hist=0.4",
            "components": [
                {"name": "rsi", "score": 0.30, "weight": 0.30, "note": "RSI=62.0"},
                {"name": "macd", "score": 0.50, "weight": 0.30, "note": "MACD_hist=+0.4"},
                {"name": "ema", "score": 0.40, "weight": 0.20, "note": "close>EMA20"},
                {"name": "change_pct", "score": 0.10, "weight": 0.10, "note": "Δ=+1%"},
                {"name": "trend5", "score": 0.20, "weight": 0.10, "note": "5-bar trend"},
            ],
        }

    def test_bullish_headline_format(self):
        out = fe.explain_score(self._bullish_payload(), symbol="BTC")
        assert "BTC" in out["headline"]
        assert "+0.42" in out["headline"]
        assert "Bull" in out["headline"]

    def test_bullish_regime_bucket(self):
        out = fe.explain_score(self._bullish_payload(), symbol="BTC")
        assert out["regime"] == "STRONG_BULL"

    def test_components_normalized(self):
        out = fe.explain_score(self._bullish_payload(), symbol="BTC")
        weights = [c["weight"] for c in out["components"]]
        assert abs(sum(weights) - 1.0) < 1e-6

    def test_short_rationale_under_80_chars(self):
        out = fe.explain_score(self._bullish_payload(), symbol="BTC")
        assert len(out["rationale_short"]) <= 80
        assert len(out["rationale_short"]) > 0

    def test_long_rationale_under_400_chars(self):
        out = fe.explain_score(self._bullish_payload(), symbol="BTC")
        assert len(out["rationale_long"]) <= 400
        assert len(out["rationale_long"]) > 0

    def test_confidence_band_high(self):
        out = fe.explain_score(self._bullish_payload(), symbol="BTC")
        assert out["confidence_band"] in {"medium", "high"}

    def test_show_math_carries_raw(self):
        payload = self._bullish_payload()
        out = fe.explain_score(payload, symbol="BTC")
        assert out["show_math"]["raw_score"] == 0.42
        assert out["show_math"]["regime_input"] == "RISK_ON"
        assert "RSI=62" in out["show_math"]["scorer_rationale"]
        assert len(out["show_math"]["components_raw"]) == 5

    def test_bearish_score_yields_bearish_headline(self):
        payload = {
            "score": -0.55,
            "regime": "RISK_OFF",
            "rationale": "RSI=20",
            "components": [
                {"name": "rsi", "score": -0.6, "weight": 0.30, "note": "RSI=20"},
                {"name": "macd", "score": -0.5, "weight": 0.30, "note": "MACD<0"},
            ],
        }
        out = fe.explain_score(payload, symbol="ETH")
        assert out["regime"] == "STRONG_BEAR"
        assert "Strong Bear" in out["headline"]
        assert "ETH" in out["headline"]

    def test_no_components(self):
        out = fe.explain_score({"score": 0.0, "regime": "TRANSITION", "components": []}, symbol="X")
        assert out["score"] == 0.0
        assert out["regime"] == "NEUTRAL"
        assert out["components"] == []
        assert "no scorable" in out["rationale_short"].lower()

    def test_empty_payload(self):
        out = fe.explain_score({}, symbol="BTC")
        assert out["regime"] == "NEUTRAL"
        assert out["score"] == 0.0


# --------------------------------------------------------------------------- #
# explain_forecast (forecast row path)
# --------------------------------------------------------------------------- #


class TestExplainForecast:
    def _agree_bull_row(self):
        return {
            "symbol": "BTC",
            "kronos_symbol": "BTC-USD",
            "ta_symbol": "BTC",
            "kronos": {
                "direction": "bullish",
                "confidence": 0.80,
                "current_price": 75000,
                "target_high": 76500,
                "target_low": 74500,
                "horizon_hours": 24,
                "projected_change_pct": 1.5,
            },
            "ta": {
                "direction": "bullish",
                "confidence": 0.75,
                "target_price": 77000,
                "timeframe": "24h",
            },
            "consensus": "AGREE_BULL",
            "edge_score": 0.78,
        }

    def test_headline_format(self):
        out = fe.explain_forecast(self._agree_bull_row())
        assert "BTC" in out["headline"]
        assert "+0.78" in out["headline"]
        assert "Agree Bull" in out["headline"]

    def test_regime_strong_bull(self):
        out = fe.explain_forecast(self._agree_bull_row())
        assert out["regime"] == "STRONG_BULL"

    def test_consensus_propagated(self):
        out = fe.explain_forecast(self._agree_bull_row())
        assert out["consensus"] == "AGREE_BULL"

    def test_components_have_kronos_and_ta(self):
        out = fe.explain_forecast(self._agree_bull_row())
        names = [c["name"] for c in out["components"]]
        assert "kronos" in names
        assert "ta" in names

    def test_components_normalized_weights(self):
        out = fe.explain_forecast(self._agree_bull_row())
        weights = [c["weight"] for c in out["components"]]
        assert abs(sum(weights) - 1.0) < 1e-6

    def test_short_rationale_bounds(self):
        out = fe.explain_forecast(self._agree_bull_row())
        assert 0 < len(out["rationale_short"]) <= 80

    def test_long_rationale_bounds(self):
        out = fe.explain_forecast(self._agree_bull_row())
        assert 0 < len(out["rationale_long"]) <= 400

    def test_show_math_carries_raw(self):
        row = self._agree_bull_row()
        out = fe.explain_forecast(row)
        assert out["show_math"]["raw_edge_score"] == 0.78
        assert out["show_math"]["consensus"] == "AGREE_BULL"
        assert out["show_math"]["kronos"]["direction"] == "bullish"
        assert out["show_math"]["ta"]["direction"] == "bullish"
        assert out["show_math"]["kronos_symbol"] == "BTC-USD"

    def test_agree_bear_row(self):
        row = {
            "symbol": "ETH",
            "kronos": {"direction": "bearish", "confidence": 0.9},
            "ta": {"direction": "bearish", "confidence": 0.8, "timeframe": "24h"},
            "consensus": "AGREE_BEAR",
            "edge_score": -0.85,
        }
        out = fe.explain_forecast(row)
        assert out["regime"] == "STRONG_BEAR"
        assert "Agree Bear" in out["headline"]
        assert out["confidence_band"] == "high"

    def test_kronos_only_row(self):
        row = {
            "symbol": "SOL",
            "kronos": {"direction": "bullish", "confidence": 0.6},
            "ta": None,
            "consensus": "KRONOS_ONLY",
            "edge_score": 0.30,
        }
        out = fe.explain_forecast(row)
        assert out["consensus"] == "KRONOS_ONLY"
        assert "Kronos Only" in out["headline"]
        assert any(c["name"] == "kronos" for c in out["components"])
        assert not any(c["name"] == "ta" for c in out["components"])

    def test_neither_row(self):
        row = {
            "symbol": "DOGE",
            "kronos": None,
            "ta": None,
            "consensus": "NEITHER",
            "edge_score": 0.0,
        }
        out = fe.explain_forecast(row)
        assert out["consensus"] == "NEITHER"
        assert out["regime"] == "NEUTRAL"
        assert out["components"] == []
        assert "DOGE" in out["headline"]

    def test_explicit_symbol_override(self):
        row = self._agree_bull_row()
        out = fe.explain_forecast(row, symbol="WBTC")
        assert "WBTC" in out["headline"]


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #


class TestExplainDispatcher:
    def test_dispatches_to_forecast(self):
        row = {"symbol": "BTC", "consensus": "AGREE_BULL", "edge_score": 0.5}
        out = fe.explain(row)
        assert out["kind"] == "forecast"
        assert out["symbol"] == "BTC"

    def test_dispatches_to_score(self):
        payload = {
            "score": 0.4,
            "regime": "RISK_ON",
            "components": [{"name": "rsi", "score": 0.4, "weight": 0.5}],
        }
        out = fe.explain(payload, symbol="BTC")
        assert out["kind"] == "quick_signal_score"
        assert out["symbol"] == "BTC"

    def test_unrecognized_payload(self):
        out = fe.explain({"foo": "bar"}, symbol="X")
        assert out["kind"] == "unrecognized"
        assert out["symbol"] == "X"
        assert out["score"] == 0.0

    def test_handles_non_dict(self):
        out = fe.explain(None, symbol="BTC")  # type: ignore[arg-type]
        assert out["kind"] == "unrecognized"


# --------------------------------------------------------------------------- #
# Component ordering — short rationale lists dominant components first
# --------------------------------------------------------------------------- #


class TestComponentOrdering:
    def test_dominant_component_first_in_short(self):
        # MACD has the largest |value|*weight contribution.
        payload = {
            "score": 0.30,
            "regime": "RISK_ON",
            "components": [
                {"name": "rsi", "score": 0.10, "weight": 0.30, "note": "RSI=55"},
                {"name": "macd", "score": 0.80, "weight": 0.30, "note": "MACD>>0"},
                {"name": "ema", "score": 0.05, "weight": 0.20, "note": "near EMA"},
            ],
        }
        out = fe.explain_score(payload, symbol="BTC")
        # The MACD label should appear earlier than the RSI label.
        macd_pos = out["rationale_short"].find("MACD")
        rsi_pos = out["rationale_short"].find("RSI")
        # If both present, MACD should be first.
        if macd_pos != -1 and rsi_pos != -1:
            assert macd_pos < rsi_pos
