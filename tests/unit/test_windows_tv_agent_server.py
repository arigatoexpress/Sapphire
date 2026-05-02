"""Tests for the read-only Windows TradingView workbench agent."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.windows_tv_agent import server  # noqa: E402


def test_status_payload_is_healthy_when_cdp_is_reachable() -> None:
    def fake_fetcher(url: str, _timeout: float):
        if url.endswith("/json/version"):
            return {"Browser": "Chrome/123", "Protocol-Version": "1.3"}
        return [
            {
                "id": "1",
                "title": "BTCUSD - TradingView",
                "url": "https://www.tradingview.com/chart/abc/",
            }
        ]

    payload = server.build_status_payload(fetcher=fake_fetcher)

    assert payload["service"] == "windows_tv_agent"
    assert payload["status"] == "healthy"
    assert payload["mode"] == "read_only_tradingview_workbench_agent"
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["trading_execution_enabled"] is False
    assert payload["safety"]["telegram_sends_enabled"] is False
    assert payload["safety"]["browser_mutation_enabled"] is False
    assert payload["cdp"]["tradingview_tab_count"] == 1


def test_status_payload_is_agent_only_when_cdp_missing_and_not_required() -> None:
    def fake_fetcher(_url: str, _timeout: float):
        raise URLError("connection refused")

    payload = server.build_status_payload(fetcher=fake_fetcher, cdp_required=False)

    assert payload["status"] == "agent_only"
    assert payload["cdp_required"] is False
    assert payload["cdp"]["healthy"] is False
    assert payload["capabilities"]["trade_execution"] is False


def test_status_payload_is_degraded_when_cdp_required_and_missing() -> None:
    def fake_fetcher(_url: str, _timeout: float):
        raise URLError("connection refused")

    payload = server.build_status_payload(fetcher=fake_fetcher, cdp_required=True)

    assert payload["status"] == "degraded"
    assert payload["cdp_required"] is True
    assert payload["cdp"]["healthy"] is False


def test_tabs_are_read_only_and_redacted_to_hosts() -> None:
    def fake_fetcher(_url: str, _timeout: float):
        return [
            {
                "id": "1",
                "title": "TradingView Chart",
                "url": "https://www.tradingview.com/chart/private-token",
            },
            {"id": "2", "title": "Docs", "url": "https://example.com/page"},
        ]

    payload = server.list_tradingview_tabs(fetcher=fake_fetcher)

    assert payload["status"] == "ok"
    assert payload["tab_count"] == 2
    assert payload["tabs"][0]["is_tradingview"] is True
    assert payload["tabs"][0]["url_host"] == "www.tradingview.com"
    assert "private-token" not in payload["tabs"][0]["url_host"]
