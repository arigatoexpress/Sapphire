"""Test traffic must never enter the real route-usage store.

Bug found 2026-07-29, in the change that introduced the store (#994). The flush
in `_metrics_after_request` fires every 50 requests and writes to the default
path. Dashboard tests drive the Flask test client hard — running
`pytest -k dashboard` (402 tests) wrote **29 routes** into
`~/autonomy-status/logs/dashboard-route-usage.json`, topped by `GET showcase: 11`.

That is worse than untidy. This store exists to decide which of 134 `/api` routes
are dead. Synthetic test traffic reads as real demand, and it biases toward
"looks used" — so a route that should be retired gets kept, and the study that
justified the whole feature is quietly wrong.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


def test_persist_is_suppressed_under_pytest(tmp_path: Path, monkeypatch) -> None:
    """Under pytest, persistence is a no-op — no file appears at all."""
    store = tmp_path / "route-usage.json"
    monkeypatch.setattr(dashboard_app, "ROUTE_USAGE_PATH", store)
    dashboard_app._metrics_counts["GET api_synthetic"] = 999

    dashboard_app.persist_route_usage()

    assert not store.exists(), "test traffic must never reach the usage store"


def test_persist_still_works_when_explicitly_forced(tmp_path: Path, monkeypatch) -> None:
    """The suppression must be overridable, or the feature's own tests can't verify it."""
    store = tmp_path / "route-usage.json"
    monkeypatch.setattr(dashboard_app, "ROUTE_USAGE_PATH", store)
    dashboard_app._metrics_counts.clear()
    dashboard_app._metrics_counts["GET api_real"] = 3

    dashboard_app.persist_route_usage(force=True)

    assert store.exists()


def test_request_hook_does_not_write_store_under_pytest(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: drive enough requests to trip the flush; store must stay absent."""
    store = tmp_path / "route-usage.json"
    monkeypatch.setattr(dashboard_app, "ROUTE_USAGE_PATH", store)
    client = dashboard_app.app.test_client()

    for _ in range(dashboard_app._ROUTE_USAGE_FLUSH_EVERY + 5):
        client.get("/health")

    assert not store.exists(), "the 50-request flush leaked into the real store"
