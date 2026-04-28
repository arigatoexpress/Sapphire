from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.sources.news import NewsAPISource


def test_newsapi_dry_run_reads_category_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_NEWSAPI_LIVE", raising=False)
    cache = tmp_path / "news.json"
    cache.write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "title": "BTC inflow surge",
                        "description": "ETF inflow lifts market",
                        "publishedAt": datetime.now(UTC).isoformat(),
                        "category": "business",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sig = NewsAPISource(cache_path=cache).latest_for("BTC", "1h")

    assert sig is not None
    assert sig.direction == "bull"
    assert sig.raw["matched_articles"] == 1
    assert "business" in sig.raw["categories"]


def test_newsapi_live_gate_uses_x_api_key_header(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_NEWSAPI_LIVE", "1")
    monkeypatch.setenv("NEWSAPI_KEY", "test-key")
    headers_seen: list[dict[str, str]] = []

    def fake_fetch(_url, headers):
        headers_seen.append(dict(headers or {}))
        return {"articles": []}

    NewsAPISource(categories=("business",), cache_path=tmp_path / "n.json", fetcher=fake_fetch).latest_for(
        "BTC", "1h"
    )

    assert headers_seen == [{"X-Api-Key": "test-key"}]
