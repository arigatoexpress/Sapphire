"""Route-usage counters must survive restarts and must not hide rare routes.

Context (2026-07-29): deciding which of the dashboard's 134 `/api/*` routes are
dead needs a week of honest usage data. The existing per-route counters are the
right mechanism but are unusable as evidence for two reasons:

1. `_metrics_counts` lives only in process memory. The dashboard has been up
   2d 6h; any restart silently resets the study to zero.
2. `/metrics` derives its route list from `_metrics_samples`, a 2000-entry ring
   buffer that drops the oldest 10% when full. A route called once a week is
   evicted and disappears from `/metrics` entirely, even though its count is
   still in `_metrics_counts`. The endpoint under-reports precisely the rare
   routes a deletion study exists to find — the most dangerous possible bias.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


def setup_function() -> None:
    dashboard_app._metrics_counts.clear()
    dashboard_app._metrics_totals.clear()
    dashboard_app._metrics_samples.clear()


teardown_function = setup_function


def test_rare_route_survives_sample_ring_eviction() -> None:
    """A route whose samples aged out must still be reported, with its count.

    This is the bias that would have made a deletion study lie: the ring buffer
    evicts oldest-first, so the least-used routes vanish first.
    """
    dashboard_app._metrics_counts["GET api_rarely_used"] = 1
    # No sample retained for it — evicted. A busy route still has samples.
    dashboard_app._metrics_counts["GET api_busy"] = 5000
    dashboard_app._metrics_samples.append(("GET", "api_busy", 12.0))

    report = dashboard_app.build_route_usage_report()
    routes = {r["route"]: r for r in report["routes"]}

    assert "GET api_rarely_used" in routes, "evicted route must not disappear"
    assert routes["GET api_rarely_used"]["count"] == 1
    assert routes["GET api_busy"]["count"] == 5000


def test_route_with_no_samples_reports_null_latency_not_zero() -> None:
    """Absent latency must be null. Zero would read as 'instantaneous'."""
    dashboard_app._metrics_counts["GET api_evicted"] = 3

    report = dashboard_app.build_route_usage_report()
    row = next(r for r in report["routes"] if r["route"] == "GET api_evicted")

    assert row["count"] == 3
    assert row["p95_ms"] is None
    assert row["samples"] == 0


def test_counts_persist_across_restart(tmp_path: Path, monkeypatch) -> None:
    """The whole point: a restart must not reset the study."""
    store = tmp_path / "route-usage.json"
    monkeypatch.setattr(dashboard_app, "ROUTE_USAGE_PATH", store)

    dashboard_app._metrics_counts["GET api_alpha"] = 7
    dashboard_app.persist_route_usage(force=True)

    # Simulate a restart: memory gone, disk intact.
    dashboard_app._metrics_counts.clear()
    dashboard_app.load_route_usage()

    assert dashboard_app._metrics_counts["GET api_alpha"] == 7


def test_persisted_counts_accumulate_rather_than_overwrite(tmp_path: Path, monkeypatch) -> None:
    """Two lifetimes of the same route must sum, or a week of data is meaningless."""
    store = tmp_path / "route-usage.json"
    monkeypatch.setattr(dashboard_app, "ROUTE_USAGE_PATH", store)

    dashboard_app._metrics_counts["GET api_alpha"] = 4
    dashboard_app.persist_route_usage(force=True)
    dashboard_app._metrics_counts.clear()

    dashboard_app.load_route_usage()
    dashboard_app._metrics_counts["GET api_alpha"] += 3
    dashboard_app.persist_route_usage(force=True)

    on_disk = json.loads(store.read_text())
    assert on_disk["counts"]["GET api_alpha"] == 7


def test_persistence_failure_never_breaks_the_request(tmp_path: Path, monkeypatch) -> None:
    """Telemetry must never take the dashboard down. Fail-open, by design."""
    unwritable = tmp_path / "nope" / "deep" / "route-usage.json"
    monkeypatch.setattr(dashboard_app, "ROUTE_USAGE_PATH", unwritable)

    def boom(*args, **kwargs):
        raise OSError("disk is gone")

    monkeypatch.setattr(dashboard_app.Path, "write_text", boom, raising=False)
    dashboard_app._metrics_counts["GET api_alpha"] = 1

    dashboard_app.persist_route_usage(force=True)  # must not raise


def test_load_tolerates_corrupt_store(tmp_path: Path, monkeypatch) -> None:
    """A truncated write from a hard kill must not prevent startup."""
    store = tmp_path / "route-usage.json"
    store.write_text('{"counts": {"GET api_alpha": 4')  # truncated JSON
    monkeypatch.setattr(dashboard_app, "ROUTE_USAGE_PATH", store)

    dashboard_app.load_route_usage()  # must not raise

    assert dashboard_app._metrics_counts == {}
