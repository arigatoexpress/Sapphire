"""Tests for lib.analytics.brain_accuracy — Trading Brain decision tracking."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.analytics.brain_accuracy import (
    GO_THRESHOLD,
    LEAN_THRESHOLD,
    WAIT_BAND,
    _load_decisions,
    brief_summary,
    record_decision,
    report,
)


def _fake_decision(
    symbol: str = "BTC",
    decision: str = "GO_LONG",
    direction: str = "bullish",
    confidence: float = 0.75,
    timestamp: str = "2026-04-18T12:00:00+00:00",
) -> dict:
    return {
        "symbol": symbol,
        "decision": decision,
        "direction": direction,
        "confidence": confidence,
        "timestamp": timestamp,
        "votes": [{"source": "TA", "direction": "bullish", "weight": 0.3, "detail": "test"}],
        "aggregation": {"bullish": 70.0, "bearish": 20.0, "neutral": 10.0},
        "track_record": {"modifier": 0, "reason": "test"},
    }


def test_report_empty():
    """Report on empty decision log returns zeros."""
    with patch("lib.analytics.brain_accuracy.DECISIONS_FILE", Path("/nonexistent/path")):
        r = report()
    assert r["total_decisions"] == 0
    assert r["scored"] == 0
    assert r["overall_accuracy"] is None


def test_record_and_load(tmp_path):
    """Decisions are recorded to JSONL and can be loaded back."""
    decisions_file = tmp_path / "brain_decisions.jsonl"
    with patch("lib.analytics.brain_accuracy.DECISIONS_FILE", decisions_file), \
         patch("lib.analytics.brain_accuracy.DECISIONS_DIR", tmp_path):
        record_decision(_fake_decision())
        record_decision(_fake_decision(symbol="ETH", decision="WAIT", direction="neutral"))

    lines = decisions_file.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["symbol"] == "BTC"
    assert first["decision"] == "GO_LONG"
    assert first["scored"] is False


def test_report_with_scored_decisions(tmp_path):
    """Report computes accuracy from scored decisions."""
    decisions_file = tmp_path / "brain_decisions.jsonl"
    records = [
        {"symbol": "BTC", "decision": "GO_LONG", "confidence": 0.8,
         "timestamp": "2026-04-17T12:00:00+00:00", "scored": True,
         "outcome": "correct", "pnl_pct": 0.02},
        {"symbol": "BTC", "decision": "GO_LONG", "confidence": 0.7,
         "timestamp": "2026-04-17T14:00:00+00:00", "scored": True,
         "outcome": "incorrect", "pnl_pct": -0.01},
        {"symbol": "ETH", "decision": "WAIT", "confidence": 0.5,
         "timestamp": "2026-04-17T16:00:00+00:00", "scored": True,
         "outcome": "correct", "pnl_pct": 0.005},
        {"symbol": "BTC", "decision": "LEAN_SHORT", "confidence": 0.45,
         "timestamp": "2026-04-18T10:00:00+00:00", "scored": False,
         "outcome": None, "pnl_pct": None},
    ]
    with open(decisions_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    with patch("lib.analytics.brain_accuracy.DECISIONS_FILE", decisions_file):
        r = report()

    assert r["total_decisions"] == 4
    assert r["scored"] == 3
    assert r["pending"] == 1
    assert r["overall_accuracy"] == round(2 / 3, 4)
    assert r["go_accuracy"] == 0.5  # 1/2 GO correct
    assert r["wait_accuracy"] == 1.0  # 1/1 WAIT correct
    assert "BTC" in r["by_symbol"]
    assert r["by_symbol"]["BTC"]["total"] == 2
    assert len(r["recent"]) == 3


def test_brief_summary_no_data():
    """Brief summary handles empty data gracefully."""
    with patch("lib.analytics.brain_accuracy.DECISIONS_FILE", Path("/nonexistent")):
        s = brief_summary()
    assert "No trading brain decisions" in s


def test_brief_summary_with_data(tmp_path):
    """Brief summary produces formatted text with data."""
    decisions_file = tmp_path / "brain_decisions.jsonl"
    records = [
        {"symbol": "BTC", "decision": "GO_LONG", "confidence": 0.8,
         "timestamp": "2026-04-17T12:00:00+00:00", "scored": True,
         "outcome": "correct", "pnl_pct": 0.03},
    ]
    with open(decisions_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    with patch("lib.analytics.brain_accuracy.DECISIONS_FILE", decisions_file):
        s = brief_summary()
    assert "100%" in s
    assert "1 scored" in s


def test_confidence_calibration(tmp_path):
    """Report includes confidence calibration buckets."""
    decisions_file = tmp_path / "brain_decisions.jsonl"
    records = [
        {"symbol": "BTC", "decision": "GO_LONG", "confidence": 0.8, "scored": True,
         "outcome": "correct", "timestamp": "2026-04-17T12:00:00+00:00"},
        {"symbol": "BTC", "decision": "GO_LONG", "confidence": 0.85, "scored": True,
         "outcome": "correct", "timestamp": "2026-04-17T13:00:00+00:00"},
        {"symbol": "ETH", "decision": "GO_SHORT", "confidence": 0.5, "scored": True,
         "outcome": "incorrect", "timestamp": "2026-04-17T14:00:00+00:00"},
    ]
    with open(decisions_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    with patch("lib.analytics.brain_accuracy.DECISIONS_FILE", decisions_file):
        r = report()

    assert len(r["confidence_calibration"]) > 0
    high_bucket = [b for b in r["confidence_calibration"] if b["bucket"].startswith("0.8")]
    assert high_bucket and high_bucket[0]["accuracy"] == 1.0


def test_thresholds_are_sane():
    """Scoring thresholds are within expected ranges."""
    assert 0.001 < GO_THRESHOLD < 0.05
    assert 0.001 < LEAN_THRESHOLD < GO_THRESHOLD
    assert 0.005 < WAIT_BAND < 0.10
