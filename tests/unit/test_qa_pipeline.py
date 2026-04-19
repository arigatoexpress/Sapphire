"""Tests for lib/content/qa_pipeline.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.content.qa_pipeline import run_qa  # type: ignore
from lib.content.report_generator import Report  # type: ignore


def test_run_qa_counts_report_sources_as_citations() -> None:
    report = Report(
        kind="weekly_crypto_brief",
        title="Brief",
        generated_at="2026-04-19T12:00:00+00:00",
        facts={
            "predictions": {"total": 120, "hits": 84, "accuracy": 0.7, "by_symbol": {}},
        },
        body=(
            "BTC closed at $65,432 yesterday. ETH gained 4.2% over 48 hours. "
            "SOL open interest rose by $120M in Q1. The funding rate hit 0.03% "
            "on three major venues. Position sizing remained at 10% of the $100K book. "
            "Another update kept the 30-day regime stable. A final note tracked 12 signals."
        ),
        sources=["data/trading_predictions.jsonl", "data/paper_portfolio.json"],
    )

    result = run_qa(report)

    assert result.passed is True
    assert "citation_quality_low" not in " ".join(result.failures)
