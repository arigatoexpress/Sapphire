"""Tests for ``services/control-plane/app/digest.py`` — Telegram message formatters.

The digest module owns the Telegram-facing alpha digest, watchlist, and
unified alpha-stream message shapes. All output is HTML-escaped, length-bounded,
and watchlist-aware. Untested before this file.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from datetime import UTC, datetime
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
    state to avoid breaking unrelated tests.
    """
    saved = {name: sys.modules.pop(name, None) for name in ("app", "app.models", "app.digest")}
    sys.path.insert(0, str(CP_ROOT))
    try:
        importlib.invalidate_caches()
        yield
    finally:
        sys.path.remove(str(CP_ROOT))
        for name in ("app", "app.models", "app.digest"):
            sys.modules.pop(name, None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod


with _control_plane_app_namespace():
    from app.digest import (  # noqa: E402
        _mentions_line,
        _render_watchlist,
        _trim,
        format_alpha_stream_message,
        format_digest_message,
        format_watchlist_message,
    )
    from app.models import ChatConfig, NewsItem, NewsSource, ScoredNews  # noqa: E402


NOW = datetime(2026, 4, 27, 14, 30, 0, tzinfo=UTC)


def _config(*, aster=None, lighter=None, extra=None) -> ChatConfig:
    return ChatConfig(
        chat_id=1,
        aster_assets=list(aster or []),
        lighter_assets=list(lighter or []),
        extra_keywords=list(extra or []),
    )


def _scored(
    *,
    title: str = "Bitcoin rallies",
    summary: str = "Growth resumes",
    alpha: int = 80,
    bias: str = "Bullish",
    confidence: str = "high",
    sentiment: int = 2,
    asset_hits=None,
    keyword_hits=None,
    rationale: str = "assets: BTC; sentiment=2",
    item_id: str = "n1",
    source_name: str = "Test Wire",
    url: str = "https://example.test/n1",
) -> ScoredNews:
    return ScoredNews(
        item=NewsItem(
            id=item_id,
            title=title,
            url=url,
            summary=summary,
            published_at=NOW,
            source=NewsSource(
                key="test",
                name=source_name,
                rss_url="https://example.test/rss",
                reliability=0.9,
                category="markets",
            ),
        ),
        alpha_score=alpha,
        sentiment=sentiment,
        bias=bias,
        confidence=confidence,
        asset_hits=list(asset_hits or []),
        keyword_hits=list(keyword_hits or []),
        rationale=rationale,
    )


# ── _trim ───────────────────────────────────────────────────────────


def test_trim_under_limit_unchanged():
    assert _trim("hello", 100) == "hello"


def test_trim_at_limit_unchanged():
    assert _trim("12345", 5) == "12345"


def test_trim_over_limit_appends_ellipsis():
    result = _trim("abcdefghij", 5)
    assert result == "ab..."
    assert len(result) == 5


def test_trim_strips_trailing_whitespace_before_ellipsis():
    """When the trim cut lands on whitespace, the suffix is stripped first."""
    result = _trim("hello world   foo", 11)
    assert result.endswith("...")
    assert "  ..." not in result


# ── _render_watchlist ──────────────────────────────────────────────


def test_render_watchlist_all_empty_uses_none():
    cfg = _config()

    rendered = _render_watchlist(cfg)

    assert "Aster: none" in rendered
    assert "Lighter: none" in rendered
    assert "Extra keywords: none" in rendered


def test_render_watchlist_includes_each_section():
    cfg = _config(aster=["BTC", "ETH"], lighter=["SOL"], extra=["fed", "cpi"])

    rendered = _render_watchlist(cfg)

    assert "Aster: BTC, ETH" in rendered
    assert "Lighter: SOL" in rendered
    assert "Extra keywords: fed, cpi" in rendered


# ── _mentions_line ─────────────────────────────────────────────────


def test_mentions_line_empty_text_returns_empty():
    cfg = _config(aster=["BTC"])

    assert _mentions_line(cfg, "") == ""


def test_mentions_line_no_watchlist_returns_empty():
    cfg = _config()

    assert _mentions_line(cfg, "Bitcoin rally") == ""


def test_mentions_line_finds_word_boundary_match():
    cfg = _config(aster=["BTC", "ETH"], lighter=["SOL"])

    result = _mentions_line(cfg, "BTC and ETH up; SOL flat")

    parts = [p.strip() for p in result.split(",")]
    assert "BTC" in parts
    assert "ETH" in parts
    assert "SOL" in parts


def test_mentions_line_avoids_substring_false_positive():
    """SOL must not match SOLID, BTC must not match BTCUSDTPAIR."""
    cfg = _config(aster=["SOL", "BTC"])

    assert _mentions_line(cfg, "SOLID is a programming framework") == ""


def test_mentions_line_dedups_and_caps_at_eight():
    """Mentions are deduped via dict.fromkeys and capped at 8 entries."""
    symbols = [f"AS{i}" for i in range(15)]
    cfg = _config(aster=symbols)
    text = " ".join(symbols)

    result = _mentions_line(cfg, text)
    parts = [p.strip() for p in result.split(",")]

    assert len(parts) == 8


def test_mentions_line_skips_blank_symbols():
    cfg = _config(aster=["", "  ", "BTC"])

    assert _mentions_line(cfg, "BTC update") == "BTC"


def test_mentions_line_uppercases_text_for_match():
    """Lower-case text in the news must still match upper-case watchlist symbols."""
    cfg = _config(aster=["BTC"])

    assert _mentions_line(cfg, "btc rally") == "BTC"


# ── format_digest_message: empty ───────────────────────────────────


def test_format_digest_empty_news_returns_no_match_message():
    cfg = _config(aster=["BTC"])

    msg = format_digest_message(cfg, [], top_k=5, generated_at=NOW)

    assert "Sapphire Alpha Digest" in msg
    assert "2026-04-27 14:30 UTC" in msg
    assert "No high-confidence headlines" in msg
    assert "Aster: BTC" in msg
    assert "/setaster" not in msg
    assert "/setlighter" not in msg
    assert "/setkeywords" not in msg
    assert "owner configuration surface" in msg


# ── format_digest_message: with news ───────────────────────────────


def test_format_digest_renders_each_scored_item():
    cfg = _config(aster=["BTC"])
    items = [
        _scored(title="Bitcoin rally", item_id="b1", url="https://x.test/b1"),
        _scored(title="ETH update", item_id="e1", url="https://x.test/e1"),
    ]

    msg = format_digest_message(cfg, items, top_k=5, generated_at=NOW)

    assert "1." in msg
    assert "Bitcoin rally" in msg
    assert "https://x.test/b1" in msg
    assert "2." in msg
    assert "ETH update" in msg
    assert "Alpha 80/100" in msg
    assert "Bullish (high)" in msg
    assert "Not financial advice" in msg


def test_format_digest_respects_top_k():
    cfg = _config(aster=["BTC"])
    items = [_scored(item_id=f"n{i}", title=f"News {i}") for i in range(10)]

    msg = format_digest_message(cfg, items, top_k=3, generated_at=NOW)

    assert "1." in msg
    assert "2." in msg
    assert "3." in msg
    # 4 is the line index for "Not financial advice", not a numbered item
    assert "4. " not in msg


def test_format_digest_html_escapes_user_content():
    cfg = _config(aster=["BTC"])
    items = [_scored(title="<script>alert('xss')</script>", item_id="x1")]

    msg = format_digest_message(cfg, items, top_k=5, generated_at=NOW)

    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg


def test_format_digest_summary_overrides_used_when_provided():
    cfg = _config(aster=["BTC"])
    item = _scored(item_id="b1", summary="Original summary")

    msg = format_digest_message(
        cfg,
        [item],
        top_k=5,
        generated_at=NOW,
        summary_overrides={"b1": "Override text"},
    )

    assert "Override text" in msg
    assert "Original summary" not in msg


def test_format_digest_skips_summary_line_when_no_summary():
    cfg = _config(aster=["BTC"])
    item = _scored(item_id="b1", summary="")

    msg = format_digest_message(cfg, [item], top_k=5, generated_at=NOW)

    assert "Summary:" not in msg
    assert "Why:" in msg  # rationale always shown


def test_format_digest_includes_mentions_line_for_watchlist_match():
    cfg = _config(aster=["BTC", "ETH"])
    item = _scored(title="BTC and ETH rally", summary="Growth")

    msg = format_digest_message(cfg, [item], top_k=5, generated_at=NOW)

    assert "Mentions:" in msg
    assert "BTC" in msg
    assert "ETH" in msg


def test_format_digest_omits_mentions_line_when_no_match():
    cfg = _config(aster=["XYZ"])
    item = _scored(title="Bitcoin rally", summary="Growth")

    msg = format_digest_message(cfg, [item], top_k=5, generated_at=NOW)

    assert "Mentions:" not in msg


def test_format_digest_truncates_to_3900_chars():
    """Message body is hard-bounded to 3900 chars to fit Telegram limits."""
    cfg = _config(aster=["BTC"])
    items = [
        _scored(
            item_id=f"n{i}",
            title=f"News {i} " + ("X" * 200),
            summary="S " + ("y" * 240),
            rationale="R " + ("z" * 220),
        )
        for i in range(50)
    ]

    msg = format_digest_message(cfg, items, top_k=50, generated_at=NOW)

    assert len(msg) <= 3900


def test_format_digest_trims_long_title_in_anchor():
    cfg = _config(aster=["BTC"])
    long_title = "T" * 300
    item = _scored(title=long_title, item_id="t1")

    msg = format_digest_message(cfg, [item], top_k=5, generated_at=NOW)

    assert "T" * 300 not in msg
    assert "..." in msg


# ── format_watchlist_message ───────────────────────────────────────


def test_format_watchlist_message_includes_label_and_content():
    cfg = _config(aster=["BTC"], lighter=["ETH"])

    msg = format_watchlist_message(cfg)

    assert "<b>Current watchlist</b>" in msg
    assert "Aster: BTC" in msg
    assert "Lighter: ETH" in msg


def test_format_watchlist_message_html_escapes():
    cfg = _config(aster=["<script>"])

    msg = format_watchlist_message(cfg)

    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg


# ── format_alpha_stream_message ────────────────────────────────────


def test_format_alpha_stream_minimal_payload_includes_title():
    cfg = _config(aster=["BTC"])

    msg = format_alpha_stream_message(cfg, {})

    assert "<b>Sapphire Unified Alpha Stream</b>" in msg
    assert "Aster: BTC" in msg
    # 0 signals on minimal payload
    assert "Signals: 0/0" in msg


def test_format_alpha_stream_renders_generated_at():
    cfg = _config()
    payload = {"generated_at": "2026-04-27T14:30:00+00:00"}

    msg = format_alpha_stream_message(cfg, payload)

    assert "2026-04-27 14:30:00 UTC" in msg


def test_format_alpha_stream_handles_missing_generated_at():
    cfg = _config()

    msg = format_alpha_stream_message(cfg, {"items": []})

    # Just no stamp section — title still present.
    assert "<b>Sapphire Unified Alpha Stream</b>" in msg


def test_format_alpha_stream_renders_summary_counts():
    cfg = _config()
    payload = {
        "summary": {
            "returned_count": 5,
            "total_scored": 10,
            "watchlist_hit_count": 2,
        },
        "items": [],
    }

    msg = format_alpha_stream_message(cfg, payload)

    assert "Signals: 5/10" in msg
    assert "watchlist hits: 2" in msg


def test_format_alpha_stream_renders_items_with_assets_and_action():
    cfg = _config()
    payload = {
        "items": [
            {
                "title": "BTC up",
                "url": "https://x.test/1",
                "source": "WireOne",
                "alpha_score": 88,
                "bias": "Bullish",
                "confidence": "high",
                "asset_hits": ["BTC", "ETH"],
                "watchlist_asset_hits": ["BTC"],
                "actionability": "buy",
                "target_streams": ["telegram", "kimi"],
            },
        ],
    }

    msg = format_alpha_stream_message(cfg, payload)

    assert "BTC up" in msg
    assert "Alpha 88/100" in msg
    assert "Bullish (high)" in msg
    assert "Assets: BTC, ETH" in msg
    assert "Watchlist hits: BTC" in msg
    assert "Action: buy" in msg
    assert "Routes: telegram, kimi" in msg


def test_format_alpha_stream_caps_at_10_items():
    cfg = _config()
    payload = {
        "items": [{"title": f"Item {i}", "url": f"https://x.test/{i}"} for i in range(20)],
    }

    msg = format_alpha_stream_message(cfg, payload)

    assert "Item 0" in msg
    assert "Item 9" in msg
    # Item 10 must not appear
    assert "Item 10" not in msg


def test_format_alpha_stream_skips_non_mapping_items():
    cfg = _config()
    payload = {"items": ["not a dict", {"title": "valid", "url": "https://x.test/1"}]}

    msg = format_alpha_stream_message(cfg, payload)

    assert "valid" in msg
    # The string item is silently skipped — no crash.


def test_format_alpha_stream_html_escapes_user_strings():
    cfg = _config()
    payload = {
        "items": [{"title": "<script>", "url": "https://x.test/", "source": "<bad>"}],
    }

    msg = format_alpha_stream_message(cfg, payload)

    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg
    assert "&lt;bad&gt;" in msg


def test_format_alpha_stream_uses_default_action_when_missing():
    cfg = _config()
    payload = {"items": [{"title": "x", "url": "https://x.test/"}]}

    msg = format_alpha_stream_message(cfg, payload)

    assert "Action: monitor" in msg


def test_format_alpha_stream_omits_command_routes():
    cfg = _config()

    default_msg = format_alpha_stream_message(cfg, {})
    custom_msg = format_alpha_stream_message(
        cfg,
        {
            "routes": {
                "telegram_command": "/custom",
                "kimi_action": "custom_action",
                "system_endpoint": "/api/custom",
            },
        },
    )

    for message in (default_msg, custom_msg):
        assert "Read-only signal projection" in message
        assert "/alphastream" not in message
        assert "telegram_command" not in message
    assert "/custom" not in custom_msg
    assert "custom_action" not in custom_msg
    assert "/api/custom" not in custom_msg


def test_format_alpha_stream_truncates_to_max_chars():
    cfg = _config()
    items = [{"title": "Item " + ("X" * 300), "url": "https://x.test/" + str(i)} for i in range(20)]
    payload = {"items": items}

    msg = format_alpha_stream_message(cfg, payload, max_chars=500)

    assert len(msg) <= 500


def test_format_alpha_stream_safely_coerces_non_int_score():
    """A non-int alpha_score (e.g. None or string) does not crash."""
    cfg = _config()
    payload = {"items": [{"title": "x", "url": "https://x.test/", "alpha_score": None}]}

    msg = format_alpha_stream_message(cfg, payload)

    assert "Alpha 0/100" in msg


@pytest.mark.parametrize(
    "raw_url,expected_in_msg",
    [
        ("https://example.test/?a=b&c=d", "&amp;c=d"),
        ('https://example.test/"x', "&quot;x"),
    ],
)
def test_format_alpha_stream_quotes_url_attribute(raw_url, expected_in_msg):
    cfg = _config()
    payload = {"items": [{"title": "x", "url": raw_url}]}

    msg = format_alpha_stream_message(cfg, payload)

    assert expected_in_msg in msg
