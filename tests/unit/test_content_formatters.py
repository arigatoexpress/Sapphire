"""Tests for lib/content/formatters.py — LinkedIn, Substack, X thread formatters.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_content_formatters.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.content.formatters import (  # type: ignore
    LINKEDIN_LIMIT,
    X_TWEET_LIMIT,
    _shorten_to,
    _split_tweets,
    format_linkedin,
    format_substack,
    format_x_thread,
)
from lib.content.report_generator import Report  # type: ignore


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _crypto_report(**overrides) -> Report:
    facts = {
        "predictions": {
            "total": 120,
            "hits": 84,
            "accuracy": 0.70,
            "by_symbol": {
                "BTC": {"hits": 30, "total": 40, "accuracy": 0.75},
                "ETH": {"hits": 24, "total": 40, "accuracy": 0.60},
                "SOL": {"hits": 30, "total": 40, "accuracy": 0.75},
            },
        },
        "portfolio": {
            "capital": 103500.0,
            "pnl_pct": 3.5,
            "open_positions": 2,
            "positions": [
                {"symbol": "BTC", "side": "long", "entry_price": 65000, "stop_loss": 63000, "take_profit": 70000},
            ],
        },
        "signal_pipeline": {
            "count": 48,
            "symbols": ["BTC", "ETH", "SOL"],
        },
    }
    facts.update(overrides.get("facts", {}))
    return Report(
        kind=overrides.get("kind", "weekly_crypto_brief"),
        title="Sapphire Weekly Crypto Brief",
        generated_at="2026-04-18T09:00:00+00:00",
        facts=facts,
        body="Test body content here.",
        sources=["data/trading_predictions.jsonl", "data/paper_portfolio.json"],
        tags=["crypto", "trading", "AI"],
    )


def _ai_report(**overrides) -> Report:
    facts = {
        "event_count": 342,
        "agent_counts": {"hermes": 120, "claw": 80, "scheduler": 60},
        "device_counts": {"mac": 200, "windows": 100, "pi": 42},
        "tracked_projects": 12,
    }
    facts.update(overrides.get("facts", {}))
    return Report(
        kind="ai_intel",
        title="Sapphire AI Intel",
        generated_at="2026-04-18T09:00:00+00:00",
        facts=facts,
        body="AI intel body.",
        sources=["data/system_events.jsonl"],
        tags=["AI", "agents"],
    )


def _security_report(**overrides) -> Report:
    facts = {
        "count": 15,
        "exploited_in_wild": 3,
        "avg_cvss": 8.1,
        "top_cves": [
            {"cve": "CVE-2026-1234", "title": "Remote code execution in libssl", "exploited": True, "cvss": 9.8, "priority_score": 0.95},
            {"cve": "CVE-2026-5678", "title": "Privilege escalation in kernel", "exploited": False, "cvss": 7.2, "priority_score": 0.72},
        ],
    }
    facts.update(overrides.get("facts", {}))
    return Report(
        kind="security_digest",
        title="Security Digest",
        generated_at="2026-04-18T09:00:00+00:00",
        facts=facts,
        body="Security digest body.",
        sources=["data/threat_intel/latest.md"],
        tags=["security", "CVE"],
    )


def _unknown_report() -> Report:
    return Report(
        kind="custom_kind",
        title="Custom Report",
        generated_at="2026-04-18T09:00:00+00:00",
        facts={},
        body="Custom body content for testing unknown kind fallback.",
        sources=["data/custom_source.json"],
        tags=["custom"],
    )


# ── _shorten_to ────────────────────────────────────────────────────────────────

class TestShortenTo:
    def test_short_text_unchanged(self):
        text = "Short text."
        assert _shorten_to(text, 100) == text

    def test_truncates_at_sentence_boundary(self):
        text = "First sentence. Second sentence that is much longer and gets cut off."
        result = _shorten_to(text, 20)
        assert len(result) <= 20
        assert result.endswith("…")

    def test_fallback_when_no_sentence_break(self):
        text = "x" * 200
        result = _shorten_to(text, 50)
        assert len(result) <= 51  # limit - 1 + ellipsis
        assert result.endswith("…")

    def test_exact_limit_not_truncated(self):
        text = "a" * 100
        assert _shorten_to(text, 100) == text


# ── _split_tweets ──────────────────────────────────────────────────────────────

class TestSplitTweets:
    def test_single_short_part(self):
        tweets = _split_tweets(["Short tweet."])
        assert len(tweets) == 1
        assert "(1/1)" in tweets[0]

    def test_multiple_parts_merged(self):
        parts = ["A.", "B.", "C."]
        tweets = _split_tweets(parts, limit=100)
        assert all(len(t) <= 100 for t in tweets)

    def test_numbering_format(self):
        parts = ["x" * 200, "y" * 200]
        tweets = _split_tweets(parts, limit=270)
        assert all("/" in t for t in tweets)

    def test_empty_parts_ignored(self):
        tweets = _split_tweets(["", "  ", "Valid tweet."])
        assert len(tweets) == 1

    def test_all_tweets_within_limit(self):
        parts = [f"Part {i}: " + "word " * 20 for i in range(10)]
        tweets = _split_tweets(parts, limit=270)
        assert all(len(t) <= 270 for t in tweets)


# ── format_linkedin ─────────────────────────────────────────────────────────────

class TestFormatLinkedIn:
    def test_crypto_report_returns_string(self):
        result = format_linkedin(_crypto_report())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_crypto_within_limit(self):
        result = format_linkedin(_crypto_report())
        assert len(result) <= LINKEDIN_LIMIT

    def test_crypto_contains_accuracy(self):
        result = format_linkedin(_crypto_report())
        assert "70.0%" in result

    def test_ai_report_dispatches(self):
        result = format_linkedin(_ai_report())
        assert isinstance(result, str)
        assert len(result) <= LINKEDIN_LIMIT

    def test_ai_contains_event_count(self):
        result = format_linkedin(_ai_report())
        assert "342" in result

    def test_security_report_dispatches(self):
        result = format_linkedin(_security_report())
        assert isinstance(result, str)

    def test_security_contains_cve_count(self):
        result = format_linkedin(_security_report())
        assert "15" in result

    def test_unknown_kind_fallback(self):
        result = format_linkedin(_unknown_report())
        assert isinstance(result, str)
        assert len(result) <= LINKEDIN_LIMIT

    def test_tags_included(self):
        result = format_linkedin(_crypto_report())
        assert "#crypto" in result or "#trading" in result or "#AI" in result


# ── format_substack ────────────────────────────────────────────────────────────

class TestFormatSubstack:
    def test_returns_markdown(self):
        result = format_substack(_crypto_report())
        assert result.startswith("#")

    def test_contains_title(self):
        result = format_substack(_crypto_report())
        assert "Sapphire Weekly Crypto Brief" in result

    def test_contains_generated_at(self):
        result = format_substack(_crypto_report())
        assert "2026-04-18" in result

    def test_contains_body(self):
        result = format_substack(_crypto_report())
        assert "Test body content" in result

    def test_contains_sources_section(self):
        result = format_substack(_crypto_report())
        assert "Data Sources" in result
        assert "data/trading_predictions.jsonl" in result

    def test_empty_sources_renders_none(self):
        r = _crypto_report()
        r.sources = []
        result = format_substack(r)
        assert "(none)" in result


# ── format_x_thread ────────────────────────────────────────────────────────────

class TestFormatXThread:
    def test_crypto_returns_list(self):
        result = format_x_thread(_crypto_report())
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_all_tweets_within_limit(self):
        result = format_x_thread(_crypto_report())
        assert all(len(t) <= X_TWEET_LIMIT for t in result)

    def test_ai_thread_returns_list(self):
        result = format_x_thread(_ai_report())
        assert isinstance(result, list)

    def test_security_thread_returns_list(self):
        result = format_x_thread(_security_report())
        assert isinstance(result, list)

    def test_market_pulse_single_tweet(self):
        r = Report(
            kind="market_pulse",
            title="Pulse",
            generated_at="2026-04-18T09:00:00",
            facts={},
            body="BTC up 3%. ETH steady. SOL breaking out.",
            sources=[],
            tags=[],
        )
        result = format_x_thread(r)
        assert len(result) == 1

    def test_market_pulse_truncated_if_too_long(self):
        long_body = "x" * 500
        r = Report(
            kind="market_pulse",
            title="Pulse",
            generated_at="2026-04-18T09:00:00",
            facts={},
            body=long_body,
            sources=[],
            tags=[],
        )
        result = format_x_thread(r)
        assert len(result[0]) <= X_TWEET_LIMIT
        assert result[0].endswith("…")

    def test_unknown_kind_uses_title_and_body(self):
        result = format_x_thread(_unknown_report())
        assert isinstance(result, list)
        assert len(result) >= 1
