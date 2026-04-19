"""Tests for the legacy Kronos compatibility wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import kronos_predict as legacy


def test_action_forecast_adapts_canonical_predictor(monkeypatch):
    """Legacy forecast should adapt canonical output and normalize symbols."""

    def fake_action_predict(**kwargs):
        assert kwargs["symbol"] == "BTC-USD"
        assert kwargs["predict_bars"] == 24
        return {
            "current_price": 100.0,
            "direction": "bullish",
            "model": "Kronos-base",
            "predictions": [
                {"close": 101.0},
                {"close": 105.0},
            ],
        }

    monkeypatch.setattr(legacy.predict_kronos, "action_predict", fake_action_predict)

    got = legacy.action_forecast("BTC", horizon=24)

    assert got["success"] is True
    assert got["symbol"] == "BTC"
    assert got["canonical_symbol"] == "BTC-USD"
    assert got["direction"] == "bullish"
    assert got["predicted_close"] == 105.0
    assert got["change_pct"] == 5.0
    assert got["horizon"] == 2


def test_action_forecast_preserves_errors(monkeypatch):
    """Legacy forecast should surface canonical errors cleanly."""

    def fake_action_predict(**kwargs):
        return {"error": "model unavailable"}

    monkeypatch.setattr(legacy.predict_kronos, "action_predict", fake_action_predict)

    assert legacy.action_forecast("ETH", horizon=12) == {"error": "model unavailable"}
