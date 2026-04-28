"""Guardrails for dashboard API caching on slow overview dependencies."""

from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")
APP_SOURCE = ROOT / "services" / "dashboard" / "app.py"


def setup_function() -> None:
    dashboard_app._cache.clear()
    dashboard_app._cache_time.clear()


def teardown_function() -> None:
    dashboard_app._cache.clear()
    dashboard_app._cache_time.clear()


def test_get_cached_respects_route_ttl(monkeypatch) -> None:
    now = {"value": 1_000.0}
    calls: list[int] = []

    monkeypatch.setattr(dashboard_app.time, "time", lambda: now["value"])

    def fetch() -> dict[str, int]:
        calls.append(1)
        return {"calls": len(calls)}

    assert dashboard_app.get_cached("route", fetch, ttl=60) == {"calls": 1}

    now["value"] += 30
    assert dashboard_app.get_cached("route", fetch, ttl=60) == {"calls": 1}

    now["value"] += 31
    assert dashboard_app.get_cached("route", fetch, ttl=60) == {"calls": 2}


def test_get_cached_returns_stale_data_when_refresh_fails(monkeypatch) -> None:
    now = {"value": 1_000.0}
    monkeypatch.setattr(dashboard_app.time, "time", lambda: now["value"])

    dashboard_app.get_cached("route", lambda: {"ok": True}, ttl=10)
    now["value"] += 11

    def fail() -> dict[str, bool]:
        raise RuntimeError("upstream unavailable")

    assert dashboard_app.get_cached("route", fail, ttl=10, raise_on_miss=True) == {"ok": True}


def test_slow_overview_routes_use_explicit_caches() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert "CHAIN_OVERVIEW_CACHE_DURATION = 60" in source
    assert "PORTFOLIO_CACHE_DURATION = 30" in source
    assert "CASCADE_CACHE_DURATION = 30" in source
    assert "STRATEGY_PERFORMANCE_CACHE_DURATION = 30" in source

    assert re.search(r"""["']chain_overview["'],""", source)
    assert "snapshot(alert_on_shift=False)" in source
    assert re.search(r"""["']portfolio_snapshot["'],""", source)
    assert re.search(r"""["']cascade_risk["'],""", source)
    assert re.search(r"""["']strategy_performance["'],""", source)
