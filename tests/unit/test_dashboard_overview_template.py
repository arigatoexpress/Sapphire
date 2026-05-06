"""Static guardrails for the dashboard overview template."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERVIEW = ROOT / "services" / "dashboard" / "templates" / "pages" / "overview.html"
BASE = ROOT / "services" / "dashboard" / "templates" / "base.html"
PLATFORM_API = ROOT / "services" / "dashboard" / "static" / "js" / "platform-api.js"


def test_overview_uses_current_dashboard_endpoints() -> None:
    template = OVERVIEW.read_text(encoding="utf-8")

    assert "/api/portfolio/summary" not in template
    assert "/api/cascade/risk" not in template
    assert "/api/performance/strategies" not in template
    assert "fetchJSON('/api/portfolio')" in template
    assert "fetchJSON('/api/cascade')" in template
    assert "fetchJSON('/api/strategy-performance')" in template


def test_overview_matches_live_api_shapes() -> None:
    template = OVERVIEW.read_text(encoding="utf-8")

    assert "Promise.all" in template
    assert "p.holdings" in template
    assert "h.market_value" in template
    assert "perf.overall?.win_rate" in template
    assert "ca.assets" in template
    assert "top.coin" in template
    assert "perf.by_strategy || {}" in template
    assert "regime_breakdown" not in template


def test_overview_has_summary_card_targets() -> None:
    template = OVERVIEW.read_text(encoding="utf-8")

    for element_id in (
        "kpi-equity",
        "kpi-equity-delta",
        "kpi-cascade",
        "kpi-cascade-delta",
        "kpi-perf-best",
        "kpi-perf-best-delta",
        "kpi-perf-worst",
        "kpi-perf-worst-delta",
    ):
        assert f'id="{element_id}"' in template


def test_base_template_loads_platform_api_helper() -> None:
    template = BASE.read_text(encoding="utf-8")
    helper = PLATFORM_API.read_text(encoding="utf-8")

    assert "platform-api.js" in template
    assert "window.platformApi" in helper
    assert "getStatus" in helper
    assert "getReadiness" in helper


def test_platform_api_strips_url_credentials_before_fetch() -> None:
    helper = PLATFORM_API.read_text(encoding="utf-8")

    assert "function cleanOrigin()" in helper
    assert "new URL(window.location.href)" in helper
    assert "currentUrl.username = ''" in helper
    assert "currentUrl.password = ''" in helper
    assert "new URL(path, cleanOrigin())" in helper
    assert "return url.href" in helper
