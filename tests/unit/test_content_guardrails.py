"""Targeted tests for public-performance guardrails."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.content import outreach, report_generator as rg  # type: ignore
from lib.content.performance_policy import (  # type: ignore
    MIN_PUBLIC_ACCURACY_SAMPLE,
    has_public_accuracy_track_record,
    small_sample_accuracy_notice,
)
from lib.content.report_generator import Report  # type: ignore


def _small_sample_predictions() -> dict:
    return {
        "total": 24,
        "hits": 14,
        "accuracy": 14 / 24,
        "by_symbol": {
            "BTC": {"hits": 8, "total": 12, "accuracy": 8 / 12},
            "ETH": {"hits": 6, "total": 12, "accuracy": 6 / 12},
        },
    }


def test_policy_threshold() -> None:
    assert has_public_accuracy_track_record({"total": MIN_PUBLIC_ACCURACY_SAMPLE}) is True
    assert has_public_accuracy_track_record({"total": MIN_PUBLIC_ACCURACY_SAMPLE - 1}) is False


def test_small_sample_notice_mentions_threshold() -> None:
    text = small_sample_accuracy_notice(
        _small_sample_predictions(),
        subject="The 6-factor TA model",
    )
    assert "24 scored forecasts" in text
    assert "100-call threshold" in text


def test_render_crypto_brief_suppresses_numeric_accuracy_breakdown() -> None:
    body = rg._render_crypto_brief({
        "predictions": _small_sample_predictions(),
        "latest_forecasts": [],
        "portfolio": {
            "capital": 103500.0,
            "initial_capital": 100000.0,
            "pnl_pct": 3.5,
            "open_positions": 1,
            "symbols": ["BTC"],
            "positions": [],
        },
        "signal_pipeline": {"count": 4, "sources": {}, "symbols": {"BTC": 4}},
    })
    assert "58.3%" not in body
    assert "14/24" not in body
    assert "8/12" not in body
    assert "100 scored forecasts" in body


def test_render_market_pulse_suppresses_numeric_accuracy_breakdown() -> None:
    body = rg._render_market_pulse({
        "predictions": _small_sample_predictions(),
        "forecasts": [
            {"symbol": "BTC", "direction": "UP", "target_price": 70000, "confidence": 0.62, "timeframe": "24h"}
        ],
        "portfolio": {"pnl_pct": 1.2, "open_positions": 2, "total_value": 101200},
    })
    assert "58.3%" not in body
    assert "14/24" not in body
    assert "100-call threshold" in body


def test_outreach_suppresses_numeric_accuracy_breakdown(monkeypatch) -> None:
    report = Report(
        kind="weekly_crypto_brief",
        title="Brief",
        generated_at="2026-04-19T12:00:00+00:00",
        facts={
            "predictions": _small_sample_predictions(),
            "portfolio": {"pnl_pct": 1.2, "open_positions": 2},
        },
        body="stub",
        sources=["data/trading_predictions.jsonl"],
    )
    monkeypatch.setattr(outreach.rg, "generate_weekly_crypto_brief", lambda: report)
    line, _sources = outreach._crypto_angle()
    assert "58.3%" not in line
    assert "14/24" not in line
    assert "100-call threshold" in line
