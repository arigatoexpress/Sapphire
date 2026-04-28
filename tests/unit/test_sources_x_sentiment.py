from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.sources.x_sentiment import XSentimentSource


def test_x_sentiment_empty_handle_config_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_X_SENTIMENT_LIVE", raising=False)
    assert XSentimentSource(cache_path=tmp_path / "x.json").latest_for("BTC", "1h") is None


def test_x_sentiment_scores_cached_tweets(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_X_SENTIMENT_LIVE", raising=False)
    cache = tmp_path / "x.json"
    cache.write_text(
        json.dumps(
            {
                "tweets": [
                    {
                        "text": "BTC breakout and inflow",
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sig = XSentimentSource(handles=["glassnode"], cache_path=cache).latest_for("BTC", "1h")

    assert sig is not None
    assert sig.direction == "bull"
    assert sig.raw["handles"] == ["glassnode"]
    assert sig.raw["live_operator_flag"] is False
