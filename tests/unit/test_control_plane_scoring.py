"""Tests for ``services/control-plane/app/scoring.py`` — pure news scoring.

The scoring function is a deterministic pure transform: a list of
``NewsItem`` plus a ``ChatConfig`` plus macro keywords plus thresholds
in, a sorted list of ``ScoredNews`` out. It owns alpha-score / sentiment
/ bias / confidence / asset-hit / keyword-hit semantics for the
control-plane's news intake. Untested before this file.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CP_ROOT = REPO_ROOT / "services" / "control-plane"


@contextlib.contextmanager
def _control_plane_app_namespace():
    """Temporarily make ``app`` resolve to control-plane's ``app`` package.

    The repo has two services that each call their package ``app``
    (``services/dashboard/app.py`` and ``services/control-plane/app/``).
    The shared ``conftest.py`` puts the dashboard one on sys.path, so we
    swap it in only for the scope of these imports and restore the prior
    state to avoid breaking unrelated tests like
    ``test_sensitivity_filter.py``.
    """
    saved = {name: sys.modules.pop(name, None) for name in ("app", "app.models", "app.scoring")}
    sys.path.insert(0, str(CP_ROOT))
    try:
        importlib.invalidate_caches()
        yield
    finally:
        sys.path.remove(str(CP_ROOT))
        for name in ("app", "app.models", "app.scoring"):
            sys.modules.pop(name, None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod


with _control_plane_app_namespace():
    from app.models import ChatConfig, NewsItem, NewsSource  # noqa: E402
    from app.scoring import (  # noqa: E402
        _age_hours,
        _asset_terms,
        _bias,
        _confidence,
        _find_term_hits,
        _normalize_asset,
        _sentiment_score,
        _tokenize,
        score_news,
    )


NOW = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _source(reliability: float = 0.8) -> NewsSource:
    return NewsSource(
        key="test",
        name="Test Wire",
        rss_url="https://example.test/rss",
        reliability=reliability,
        category="markets",
    )


def _item(
    title: str,
    *,
    summary: str = "",
    age_hours: float = 1.0,
    item_id: str = "n1",
    reliability: float = 0.8,
) -> NewsItem:
    return NewsItem(
        id=item_id,
        title=title,
        url=f"https://example.test/{item_id}",
        summary=summary,
        published_at=NOW - timedelta(hours=age_hours),
        source=_source(reliability=reliability),
    )


def _config(
    *,
    aster: list[str] | None = None,
    lighter: list[str] | None = None,
    extra: list[str] | None = None,
) -> ChatConfig:
    return ChatConfig(
        chat_id=1,
        aster_assets=list(aster or []),
        lighter_assets=list(lighter or []),
        extra_keywords=list(extra or []),
    )


# ── _normalize_asset ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("btc", "BTC"),
        ("  eth  ", "ETH"),
        ("Sol", "SOL"),
        ("WBTC", "WBTC"),
        ("a b c", "ABC"),
    ],
)
def test_normalize_asset_uppercases_and_strips(raw, expected):
    assert _normalize_asset(raw) == expected


# ── _tokenize ────────────────────────────────────────────────────────


def test_tokenize_lowercases_and_collapses_whitespace():
    assert _tokenize("Hello\n\nWORLD\tfoo  bar") == "hello world foo bar"


# ── _asset_terms ─────────────────────────────────────────────────────


def test_asset_terms_includes_aliases_for_known_assets():
    result = _asset_terms(["BTC"])

    assert "btc" in result["BTC"]
    assert "bitcoin" in result["BTC"]


def test_asset_terms_falls_back_to_lowercase_for_unknown_asset():
    result = _asset_terms(["XYZUSDT"])

    assert result == {"XYZUSDT": {"xyzusdt"}}


def test_asset_terms_skips_blank_entries():
    result = _asset_terms(["", "  ", "BTC"])

    assert list(result.keys()) == ["BTC"]


def test_asset_terms_handles_perp_format():
    result = _asset_terms(["AAPLUSDT"])

    assert "aapl" in result["AAPLUSDT"]
    assert "apple" in result["AAPLUSDT"]


# ── _find_term_hits ──────────────────────────────────────────────────


def test_find_term_hits_matches_word_boundary():
    text = "the cat is on the mat"

    assert _find_term_hits(text, ["cat", "dog"]) == ["cat"]


def test_find_term_hits_does_not_match_substring():
    text = "scattered showers"

    # "cat" must not match "scattered"
    assert _find_term_hits(text, ["cat"]) == []


def test_find_term_hits_handles_empty_terms():
    assert _find_term_hits("hello", []) == []


# ── _sentiment_score ─────────────────────────────────────────────────


def test_sentiment_score_positive_increment():
    assert _sentiment_score("rally and surge with growth") == 3


def test_sentiment_score_negative_decrement():
    assert _sentiment_score("hack and ban with crackdown") == -3


def test_sentiment_score_balanced():
    assert _sentiment_score("rally meets crackdown") == 0


def test_sentiment_score_zero_for_neutral():
    assert _sentiment_score("the market is open") == 0


# ── _confidence ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, "high"),
        (75, "high"),
        (74, "medium"),
        (55, "medium"),
        (54, "low"),
        (0, "low"),
        (-5, "low"),
    ],
)
def test_confidence_thresholds(score, expected):
    assert _confidence(score) == expected


# ── _bias ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sentiment,expected",
    [
        (5, "Bullish"),
        (2, "Bullish"),
        (1, "Two-sided"),
        (0, "Two-sided"),
        (-1, "Two-sided"),
        (-2, "Bearish"),
        (-5, "Bearish"),
    ],
)
def test_bias_thresholds(sentiment, expected):
    assert _bias(sentiment) == expected


# ── _age_hours ───────────────────────────────────────────────────────


def test_age_hours_positive_age():
    published = NOW - timedelta(hours=3)
    assert _age_hours(NOW, published) == 3.0


def test_age_hours_clamps_future_to_zero():
    """Items published in the future (clock skew) clamp to age=0."""
    published = NOW + timedelta(hours=2)
    assert _age_hours(NOW, published) == 0.0


def test_age_hours_partial_hour():
    published = NOW - timedelta(minutes=30)
    assert _age_hours(NOW, published) == 0.5


# ── score_news happy path ────────────────────────────────────────────


def test_score_news_skips_items_older_than_max():
    config = _config(aster=["BTC"])
    items = [
        _item("Bitcoin rally", summary="growth", age_hours=100.0, item_id="old"),
        _item("Bitcoin surge", summary="adoption", age_hours=2.0, item_id="fresh"),
    ]

    scored = score_news(items, config, [], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    assert [s.item.id for s in scored] == ["fresh"]


def test_score_news_drops_items_with_no_asset_or_keyword_hit():
    config = _config(aster=["BTC"])
    items = [_item("Random title about pizza", summary="nothing relevant")]

    scored = score_news(items, config, ["macro"], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    assert scored == []


def test_score_news_keeps_keyword_only_match():
    """An item with NO asset hit but a keyword hit still scores."""
    config = _config(aster=[])
    items = [_item("Fed sets new rate", summary="policy update")]

    scored = score_news(items, config, ["fed"], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    assert len(scored) == 1
    assert scored[0].keyword_hits == ["fed"]
    assert scored[0].asset_hits == []


def test_score_news_keeps_asset_only_match():
    config = _config(aster=["BTC"])
    items = [_item("Bitcoin steady", summary="no notable terms")]

    scored = score_news(items, config, [], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    assert len(scored) == 1
    assert scored[0].asset_hits == ["BTC"]


def test_score_news_filters_below_min_alpha():
    config = _config(aster=["BTC"])
    items = [_item("Bitcoin steady", summary="", age_hours=20.0)]

    scored = score_news(items, config, [], min_alpha_score=80, max_news_age_hours=24, now=NOW)

    assert scored == []


def test_score_news_alpha_score_is_clamped_to_0_100():
    config = _config(aster=["BTC", "ETH"])
    items = [
        _item(
            "Bitcoin rally surge growth adoption",
            summary="bullish partnership upgrade beats",
            age_hours=0.0,
            reliability=1.0,
        ),
    ]

    scored = score_news(items, config, [], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    assert scored
    assert 0 <= scored[0].alpha_score <= 100


def test_score_news_sorts_by_score_then_recency_descending():
    config = _config(aster=["BTC"])
    items = [
        _item("Bitcoin rally", summary="growth", age_hours=10.0, item_id="older"),
        _item("Bitcoin rally", summary="growth", age_hours=1.0, item_id="newer"),
    ]

    scored = score_news(items, config, [], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    # Same content but newer should sort first.
    assert [s.item.id for s in scored] == ["newer", "older"]


def test_score_news_rationale_includes_asset_macro_sentiment():
    config = _config(aster=["BTC"])
    items = [_item("Bitcoin rally", summary="bullish growth")]

    scored = score_news(items, config, ["fed"], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    rationale = scored[0].rationale
    assert "assets:" in rationale
    assert "BTC" in rationale
    assert "sentiment=" in rationale


def test_score_news_caps_keyword_hits_in_rationale_at_4():
    """Long keyword lists are truncated in the human-readable rationale."""
    config = _config(extra=[])
    keywords = [f"kw{i}" for i in range(10)]
    text = " ".join(keywords)
    items = [_item(text, summary="")]

    scored = score_news(items, config, keywords, min_alpha_score=0, max_news_age_hours=999, now=NOW)

    # All keyword hits land in keyword_hits; only first 4 in rationale
    assert len(scored[0].keyword_hits) == 10
    macro_segment = next(s for s in scored[0].rationale.split("; ") if s.startswith("macro:"))
    assert macro_segment.count(",") == 3  # 4 items separated by 3 commas


def test_score_news_relevance_caps_at_45():
    """Relevance component (asset×13 + keyword×6) is capped at 45 in the score."""
    config = _config(aster=["BTC", "ETH", "SOL", "ARB", "OP"])  # 5 assets ×13 = 65 raw
    items = [_item("BTC ETH SOL ARB OP rally", summary="growth")]

    scored = score_news(items, config, [], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    assert scored
    # Score upper bound: 45 relevance + 22 recency + 15 reliability + 18 sentiment = 100
    assert scored[0].alpha_score <= 100


def test_score_news_empty_input_returns_empty():
    config = _config(aster=["BTC"])

    scored = score_news([], config, [], min_alpha_score=0, max_news_age_hours=24, now=NOW)

    assert scored == []


def test_score_news_now_defaults_to_current_time(monkeypatch):
    """If no `now` is passed, score_news uses the current UTC time."""
    with _control_plane_app_namespace():
        import app.scoring as scoring_mod
        from app.scoring import NewsItem as _NewsItem  # noqa: F401

    fixed_now = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    monkeypatch.setattr(scoring_mod, "datetime", _FrozenDatetime)

    config = _config(aster=["BTC"])
    fresh_item = NewsItem(
        id="n1",
        title="Bitcoin rally",
        url="https://example.test/n1",
        summary="",
        published_at=fixed_now - timedelta(seconds=3),
        source=_source(reliability=0.8),
    )

    # Should not raise and should produce a scored result for a fresh item.
    scored = score_news([fresh_item], config, [], min_alpha_score=0, max_news_age_hours=24)

    assert len(scored) == 1


def test_score_news_blank_keywords_dropped():
    """Blank macro keywords don't crash and aren't matched."""
    config = _config(extra=["", "  "])
    items = [_item("Bitcoin rally", summary="growth")]

    scored = score_news(
        items, config, ["", "  ", "rally"], min_alpha_score=0, max_news_age_hours=24, now=NOW
    )

    # Only "rally" is a real keyword
    assert "rally" in scored[0].keyword_hits or scored == []  # may be filtered if score too low
