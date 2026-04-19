"""Tests for the trading_brain tool."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "lib"))

_spec = importlib.util.spec_from_file_location("trading_brain", TOOLS / "internal" / "trading_brain.py")
tb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tb)


def test_action_decide_uses_canonical_kronos_tool(monkeypatch):
    """Trading brain should call predict_kronos with canonicalized symbols."""
    calls: list[tuple[str, dict]] = []

    def fake_run_tool(name: str, params: dict) -> dict:
        calls.append((name, params))
        if name == "signal_generator":
            return {"signals": 0, "details": []}
        if name == "predict_kronos":
            return {
                "direction": "bullish",
                "current_price": 100.0,
                "predictions": [{"close": 103.0}, {"close": 106.0}],
            }
        if name == "paper_trader":
            return {"total_trades": 0}
        return {"error": f"unexpected tool: {name}"}

    fake_profile = SimpleNamespace(
        net_signal="bullish",
        rsi_14=62.0,
        ma_trend="up",
        signal_count_bullish=3,
        signal_count_bearish=1,
    )

    monkeypatch.setattr(tb, "_run_tool", fake_run_tool)
    monkeypatch.setattr(tb, "_get_macro_sentiment", lambda: {"sentiment": "neutral", "score": 0, "reasons": []})
    monkeypatch.setattr(tb, "_get_paper_track_record", lambda: {"modifier": 0, "reason": "no track record"})
    monkeypatch.setitem(sys.modules, "technical_analysis", SimpleNamespace(analyze=lambda symbol: fake_profile))

    got = tb.action_decide("BTC")

    kronos_calls = [params for name, params in calls if name == "predict_kronos"]
    assert len(kronos_calls) == 1
    assert kronos_calls[0]["symbol"] == "BTC-USD"
    assert kronos_calls[0]["action"] == "predict"
    assert got["decision"] in {"GO_LONG", "LEAN_LONG"}
    assert any(v["source"] == "Kronos" for v in got["votes"])
