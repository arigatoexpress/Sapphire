"""Tests for services/analytics_dashboard/app.py — Cloud Run analytics service.

Covers everything that the existing ``test_analytics_probe_sink.py`` does
*not* cover:

    * ``_jsonable``  — datetime serialization helper
    * ``_clean``     — row sanitization
    * ``_rows``      — BigQuery client invocation contract
    * ``healthz`` aliases — /health, /healthz, /healthz/, /_ah/health
    * ``firebase_hosting_verification``
    * ``index``      — template rendering
    * ``summary``, ``performance``, ``regime``, ``predictions``, ``threats``,
      ``signals_recent`` — JSON shape, query parameter wiring

We mock ``google.cloud.bigquery`` at import time (mirroring the existing
probe-sink test pattern) so no GCP creds are required, then patch
``app._rows`` per-test to provide controlled fixtures.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "services" / "analytics_dashboard" / "app.py"


def _install_fake_bigquery(monkeypatch) -> tuple[types.ModuleType, list]:
    """Install a fake google.cloud.bigquery into sys.modules.

    Returns the fake ``bigquery`` module and a list that records every
    ``ScalarQueryParameter`` instance constructed during the test, so callers
    can assert on the parameter wiring.
    """
    captured_params: list = []

    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_bigquery.Client = lambda project: types.SimpleNamespace(project=project)

    def _qjc(query_parameters=None):
        return types.SimpleNamespace(query_parameters=query_parameters or [])

    def _sqp(name, kind, value):
        sp = types.SimpleNamespace(name=name, kind=kind, value=value)
        captured_params.append(sp)
        return sp

    fake_bigquery.QueryJobConfig = _qjc
    fake_bigquery.ScalarQueryParameter = _sqp
    fake_cloud.bigquery = fake_bigquery

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("BQ_DATASET", "test_dataset")
    return fake_bigquery, captured_params


def _load_app(monkeypatch):
    """Load app.py fresh against the fake bigquery shim. Returns the module."""
    _install_fake_bigquery(monkeypatch)
    module_name = "sapphire_test_analytics_dashboard_app"
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


@pytest.fixture
def app_module(monkeypatch):
    module = _load_app(monkeypatch)
    yield module
    sys.modules.pop("sapphire_test_analytics_dashboard_app", None)


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


# ---------------------------------------------------------------------------
# _jsonable / _clean
# ---------------------------------------------------------------------------


def test_jsonable_serializes_datetime_to_iso(app_module):
    dt = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    out = app_module._jsonable(dt)
    assert out == dt.isoformat()


def test_jsonable_passes_through_primitive_types(app_module):
    assert app_module._jsonable(42) == 42
    assert app_module._jsonable("hi") == "hi"
    assert app_module._jsonable(None) is None
    assert app_module._jsonable(3.14) == 3.14
    assert app_module._jsonable(True) is True


def test_jsonable_passes_through_lists_and_dicts_unchanged(app_module):
    """_jsonable doesn't recurse — lists and dicts are returned as-is.
    Recursion is handled at the row level by _clean.
    """
    assert app_module._jsonable([1, 2, 3]) == [1, 2, 3]
    assert app_module._jsonable({"k": "v"}) == {"k": "v"}


def test_clean_converts_datetimes_in_rows(app_module):
    dt = datetime(2026, 4, 28, 9, 30, tzinfo=UTC)
    rows = [{"timestamp": dt, "symbol": "BTC"}]
    cleaned = app_module._clean(rows)
    assert cleaned == [{"timestamp": dt.isoformat(), "symbol": "BTC"}]


def test_clean_handles_empty_input(app_module):
    assert app_module._clean([]) == []


def test_clean_does_not_mutate_input_rows(app_module):
    dt = datetime(2026, 4, 28, tzinfo=UTC)
    original = [{"ts": dt}]
    _ = app_module._clean(original)
    # original row's value should still be a datetime, not a string
    assert isinstance(original[0]["ts"], datetime)


def test_clean_processes_multiple_rows_independently(app_module):
    rows = [
        {"a": 1, "ts": datetime(2026, 1, 1, tzinfo=UTC)},
        {"a": 2, "ts": datetime(2026, 2, 1, tzinfo=UTC)},
    ]
    cleaned = app_module._clean(rows)
    assert cleaned == [
        {"a": 1, "ts": datetime(2026, 1, 1, tzinfo=UTC).isoformat()},
        {"a": 2, "ts": datetime(2026, 2, 1, tzinfo=UTC).isoformat()},
    ]


# ---------------------------------------------------------------------------
# _rows — BigQuery contract
# ---------------------------------------------------------------------------


def _attach_fake_query(app_module, monkeypatch, fake_query):
    """Install fake_query as a method on the module-level bq client."""
    fake_client = types.SimpleNamespace(project="test-project", query=fake_query)
    monkeypatch.setattr(app_module, "bq", fake_client)


def test_rows_invokes_bq_query_with_params(app_module, monkeypatch):
    captured: dict = {}

    class _FakeJob:
        def result(self):
            return iter([{"foo": 1}, {"foo": 2}])

    def fake_query(sql, job_config):
        captured["sql"] = sql
        captured["job_config"] = job_config
        return _FakeJob()

    _attach_fake_query(app_module, monkeypatch, fake_query)

    sample_param = app_module.bigquery.ScalarQueryParameter("days", "INT64", 7)
    out = app_module._rows("SELECT 1", params=[sample_param])

    assert out == [{"foo": 1}, {"foo": 2}]
    assert captured["sql"] == "SELECT 1"
    assert captured["job_config"].query_parameters == [sample_param]


def test_rows_defaults_to_empty_param_list(app_module, monkeypatch):
    captured: dict = {}

    class _FakeJob:
        def result(self):
            return iter([])

    def fake_query(sql, job_config):
        captured["params"] = job_config.query_parameters
        return _FakeJob()

    _attach_fake_query(app_module, monkeypatch, fake_query)

    out = app_module._rows("SELECT 1")

    assert out == []
    assert captured["params"] == []


def test_rows_returns_list_of_plain_dicts(app_module, monkeypatch):
    """Each row must be coerced to dict() — bigquery Row objects are Mapping but
    not dict, and downstream JSON serializers occasionally require literal dicts.
    """

    class _FakeJob:
        def result(self):
            class _RowLike:
                def __init__(self, items):
                    self._items = items

                def keys(self):
                    return [k for k, _ in self._items]

                def __getitem__(self, k):
                    return dict(self._items)[k]

                def __iter__(self):
                    return iter(self._items)

            yield _RowLike([("symbol", "BTC"), ("price", 70000)])

    _attach_fake_query(app_module, monkeypatch, lambda sql, job_config: _FakeJob())

    out = app_module._rows("SELECT 1")

    assert out == [{"symbol": "BTC", "price": 70000}]
    assert all(type(r) is dict for r in out)  # noqa: E721 — strict dict check intended


# ---------------------------------------------------------------------------
# health endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/health", "/healthz", "/healthz/", "/_ah/health"])
def test_healthz_aliases_all_return_200(client, path):
    response = client.get(path)
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["project"] == "test-project"
    assert body["dataset"] == "test_dataset"
    assert "ts" in body


def test_healthz_timestamp_is_iso8601(client):
    body = client.get("/healthz").get_json()
    parsed = datetime.fromisoformat(body["ts"])
    # Must be within a sensible window (server clock + this test).
    delta = abs((datetime.now(UTC) - parsed).total_seconds())
    assert delta < 60.0


def test_firebase_verification_returns_plain_text_ok(client):
    response = client.get("/__/hosting/verification")
    assert response.status_code == 200
    assert response.text == "ok\n"
    assert response.headers["Content-Type"] == "text/plain"
    assert response.headers["Cache-Control"] == "no-store"


# ---------------------------------------------------------------------------
# JSON endpoints — patch _rows directly
# ---------------------------------------------------------------------------


def test_summary_endpoint_returns_first_row_as_object(client, app_module, monkeypatch):
    summary_row = {
        "signals": 100,
        "predictions": 42,
        "regime_snapshots": 7,
        "threats": 3,
        "leads": 11,
        "inference_metrics": 999,
        "service_health": 21,
        "total_pnl_usd": 12345.67,
        "win_rate": 0.6,
        "latest_regime": "BULL",
        "fear_greed": 55,
    }
    monkeypatch.setattr(app_module, "_rows", lambda sql, params=None: [summary_row])

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.get_json() == summary_row


def test_summary_endpoint_returns_empty_object_when_no_rows(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_rows", lambda sql, params=None: [])

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.get_json() == {}


def test_performance_endpoint_passes_days_param(client, app_module, monkeypatch):
    captured: dict = {}

    def fake_rows(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params or []
        return [
            {
                "date": datetime(2026, 4, 1, tzinfo=UTC),
                "symbol": "BTC",
                "total_signals": 12,
                "wins": 8,
                "losses": 4,
                "win_rate": 0.667,
                "daily_pnl_usd": 250.0,
                "profit_factor": 1.8,
                "avg_confidence": 0.72,
            }
        ]

    monkeypatch.setattr(app_module, "_rows", fake_rows)

    response = client.get("/api/performance?days=14")
    body = response.get_json()

    assert response.status_code == 200
    assert body["days"] == 14
    assert isinstance(body["rows"], list)
    assert body["rows"][0]["symbol"] == "BTC"
    # date must be ISO-string after _clean
    assert body["rows"][0]["date"] == datetime(2026, 4, 1, tzinfo=UTC).isoformat()
    # query param must have been built with INT64 type
    assert captured["params"][0].name == "days"
    assert captured["params"][0].kind == "INT64"
    assert captured["params"][0].value == 14


def test_performance_endpoint_uses_default_days_when_unspecified(client, app_module, monkeypatch):
    captured: dict = {}

    def fake_rows(sql, params=None):
        captured["params"] = params or []
        return []

    monkeypatch.setattr(app_module, "_rows", fake_rows)

    response = client.get("/api/performance")
    body = response.get_json()

    assert response.status_code == 200
    assert body["days"] == 30
    assert captured["params"][0].value == 30


def _capture_rows_factory(captured: dict):
    def fake_rows(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params or []
        return []

    return fake_rows


def test_regime_endpoint_passes_limit_param(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_rows_factory(captured))

    response = client.get("/api/regime?limit=25")

    assert response.status_code == 200
    assert response.get_json() == {"rows": []}
    assert captured["params"][0].name == "limit"
    assert captured["params"][0].value == 25


def test_regime_endpoint_default_limit_is_100(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_rows_factory(captured))

    client.get("/api/regime")

    assert captured["params"][0].value == 100


def test_predictions_endpoint_default_limit_is_50(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_rows_factory(captured))

    client.get("/api/predictions")

    assert captured["params"][0].value == 50


def test_predictions_endpoint_serializes_rows(client, app_module, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_rows",
        lambda sql, params=None: [
            {
                "timestamp": datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
                "symbol": "ETH",
                "model": "kronos",
                "direction": "BULL",
                "confidence": 0.85,
                "current_price": 3200.0,
                "predicted_price_24h": 3300.0,
                "predicted_move_pct": 3.125,
                "accuracy_score": 0.71,
            }
        ],
    )

    response = client.get("/api/predictions?limit=10")
    body = response.get_json()

    assert response.status_code == 200
    assert body["rows"][0]["symbol"] == "ETH"
    assert body["rows"][0]["timestamp"].endswith("+00:00")


def test_threats_endpoint_passes_days_param(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_rows_factory(captured))

    response = client.get("/api/threats?days=7")

    assert response.status_code == 200
    assert captured["params"][0].name == "days"
    assert captured["params"][0].value == 7


def test_threats_endpoint_default_days_is_30(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_rows_factory(captured))
    client.get("/api/threats")
    assert captured["params"][0].value == 30


def test_signals_recent_passes_limit_param(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_rows_factory(captured))

    response = client.get("/api/signals/recent?limit=200")

    assert response.status_code == 200
    assert captured["params"][0].name == "limit"
    assert captured["params"][0].value == 200


def test_signals_recent_default_limit_is_100(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_rows_factory(captured))
    client.get("/api/signals/recent")
    assert captured["params"][0].value == 100


def test_invalid_days_param_rejected_with_500(client, app_module, monkeypatch):
    """``int(request.args.get(...))`` raises ValueError on non-numeric input,
    which Flask surfaces as a 500. Anchor that behavior so any future input
    sanitization (e.g. clamping or 400 response) is a deliberate change.
    """
    monkeypatch.setattr(app_module, "_rows", lambda sql, params=None: [])
    response = client.get("/api/performance?days=banana")
    assert response.status_code == 500


def test_index_route_uses_template(client, app_module, monkeypatch):
    """The index endpoint renders templates/index.html with project + dataset.
    We only need to assert routing + template engine wiring, not HTML shape.
    """
    captured: dict = {}

    def fake_render(name, **ctx):
        captured["name"] = name
        captured["ctx"] = ctx
        return "RENDERED"

    monkeypatch.setattr(app_module, "render_template", fake_render)

    response = client.get("/")

    assert response.status_code == 200
    assert response.text == "RENDERED"
    assert captured["name"] == "index.html"
    assert captured["ctx"] == {"project": "test-project", "dataset": "test_dataset"}


def test_unknown_post_path_falls_through_to_probe_sink(client, app_module, monkeypatch):
    """Probe sink already covers paths in _KNOWN_PROBE_PATHS. Verify catch-all
    falls through to 404 for unknown paths (anchor the contract; existing test
    file covers known probe shapes).
    """
    monkeypatch.setattr(app_module, "_rows", lambda sql, params=None: [])
    response = client.post("/this-is-not-a-known-probe", data="x=1")
    assert response.status_code == 404


def test_summary_endpoint_serializes_datetime_in_response(client, app_module, monkeypatch):
    """Edge case: latest_regime row may include a datetime; ensure _clean kicks in."""
    monkeypatch.setattr(
        app_module,
        "_rows",
        lambda sql, params=None: [
            {
                "signals": 1,
                "last_seen": datetime(2026, 4, 28, 6, 0, tzinfo=UTC),
            }
        ],
    )

    response = client.get("/api/summary")
    body = response.get_json()

    assert body["last_seen"] == datetime(2026, 4, 28, 6, 0, tzinfo=UTC).isoformat()
