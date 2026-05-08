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
import json
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

    def _aqp(name, kind, value):
        sp = types.SimpleNamespace(name=name, kind=kind, value=value, array=True)
        captured_params.append(sp)
        return sp

    fake_bigquery.QueryJobConfig = _qjc
    fake_bigquery.ScalarQueryParameter = _sqp
    fake_bigquery.ArrayQueryParameter = _aqp
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
    # app.py imports sibling modules (`auth`, `brain`) by bare name — the
    # service's own directory is the import root on Cloud Run. Mirror that
    # here so the brain endpoints actually wire up under test.
    svc_dir = APP_PATH.parent
    monkeypatch.syspath_prepend(str(svc_dir))
    # Drop any stale brain/auth modules from a previous test run so the
    # next exec_module() picks up our shimmed sys.path.
    for name in ("brain", "auth"):
        sys.modules.pop(name, None)

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
    c = app_module.app.test_client()
    _install_test_admin_session(app_module)
    c.set_cookie("sapphire_admin", "test-admin")
    return c


class _TestAdminSession:
    def verify_session(self, token):
        if token == "test-admin":
            return {"user_id": "test-admin"}
        return None


def _install_test_admin_session(app_module):
    app_module.app.extensions["sapphire_admin_session"] = _TestAdminSession()


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


def _capture_first_call_factory(captured: dict):
    """Variant of _capture_rows_factory that only records the FIRST call.

    Some endpoints (regime) make multiple _rows calls — a parameterized
    main query plus a parameter-less meta query. The original capture
    overwrote on every call, so subsequent assertions hit the empty
    meta-call params. This wrapper preserves the first call's wiring.
    """

    def fake_rows(sql, params=None):
        if "sql" not in captured:
            captured["sql"] = sql
            captured["params"] = params or []
        return []

    return fake_rows


def test_regime_endpoint_passes_limit_param(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_first_call_factory(captured))

    response = client.get("/api/regime?limit=25")

    assert response.status_code == 200
    body = response.get_json()
    # Endpoint now also returns a meta block alongside rows; assert on the
    # parts we care about rather than strict equality.
    assert body["rows"] == []
    assert "meta" in body
    assert captured["params"][0].name == "limit"
    assert captured["params"][0].value == 25


def test_regime_endpoint_default_limit_is_100(client, app_module, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app_module, "_rows", _capture_first_call_factory(captured))

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


def test_sensitive_endpoints_require_admin_cookie(app_module):
    _install_test_admin_session(app_module)
    public = app_module.app.test_client()

    for path in [
        "/api/performance",
        "/api/predictions",
        "/api/predictions/accuracy",
        "/api/correlation/matrix",
        "/api/vpin",
        "/api/deflated-sharpe/rolling",
        "/api/timeseries/inference",
        "/api/timeseries/services",
        "/api/silos/business",
        "/api/silos/inference",
        "/api/signals/recent",
        "/api/brain/history",
        "/api/brain/correlate",
    ]:
        response = public.get(path)
        assert response.status_code == 401, path
        assert response.get_json()["error"] == "unauthorized"


def test_public_silos_health_hides_service_details(app_module, monkeypatch):
    _install_test_admin_session(app_module)
    monkeypatch.setattr(
        app_module,
        "_rows",
        lambda sql, params=None: [
            {
                "service": "secret-service",
                "status": "healthy",
                "host": "internal-host",
                "last_seen": datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
                "response_ms": 12,
            }
        ],
    )
    public = app_module.app.test_client()

    response = public.get("/api/silos/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["mode"] == "public_silos_health_summary"
    assert body["services"] == []
    assert body["service_summary"]["reporting"] == 1
    assert "admin_required_for" in body


def test_public_failover_readiness_hides_device_detail(app_module, monkeypatch):
    _install_test_admin_session(app_module)
    monkeypatch.setattr(
        app_module,
        "_rows",
        lambda sql, params=None: [
            {
                "service": "windows-secret-ollama",
                "status": "down",
                "host": "100.71.10.48",
                "last_seen": datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
                "response_ms": 999,
            },
            {
                "service": "signal-logger",
                "status": "healthy",
                "host": "mac-commander",
                "last_seen": datetime(2026, 5, 7, 12, 1, tzinfo=UTC),
                "response_ms": 12,
            },
        ],
    )
    monkeypatch.setattr(
        app_module,
        "_http_get_json",
        lambda url, timeout=3.0: {"status": "ok", "sha": "private-tho-sha"},
    )
    public = app_module.app.test_client()

    response = public.get("/api/failover/readiness")

    assert response.status_code == 200
    body = response.get_json()
    assert body["mode"] == "public_failover_readiness_summary"
    assert body["overall_status"] == "degraded_with_fallback"
    assert "compute_path" in body["degraded_lanes"]
    assert all("services" not in lane for lane in body["lanes"])
    serialized = json.dumps(body)
    assert "windows-secret-ollama" not in serialized
    assert "100.71.10.48" not in serialized
    assert "private-tho-sha" not in serialized
    assert "GPU" not in serialized
    assert "Mac" not in serialized
    assert "admin_required_for" in body


def test_admin_failover_readiness_includes_operator_detail(client, app_module, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_rows",
        lambda sql, params=None: [
            {
                "service": "windows-secret-ollama",
                "status": "down",
                "host": "100.71.10.48",
                "last_seen": datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
                "response_ms": 999,
            }
        ],
    )
    monkeypatch.setattr(
        app_module,
        "_http_get_json",
        lambda url, timeout=3.0: {"status": "ok", "sha": "private-tho-sha"},
    )

    response = client.get("/api/failover/readiness")

    assert response.status_code == 200
    body = response.get_json()
    assert body["mode"] == "admin_failover_readiness_detail"
    assert body["routing_policy"]
    serialized = json.dumps(body)
    assert "windows-secret-ollama" in serialized
    assert "100.71.10.48" in serialized
    assert "private-tho-sha" in serialized


def test_public_brain_persist_requires_admin(app_module):
    _install_test_admin_session(app_module)
    public = app_module.app.test_client()

    response = public.get("/api/brain/synthesis?persist=1")

    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


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
    assert captured["ctx"]["project"] == "test-project"
    assert captured["ctx"]["dataset"] == "test_dataset"
    assert [tab["slug"] for tab in captured["ctx"]["project_tabs"]]


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


# ---------------------------------------------------------------------------
# Sapphire Brain hero panel — render + endpoint wiring
# ---------------------------------------------------------------------------


def test_brain_endpoints_are_registered_on_app(app_module):
    """register_brain() should attach the three /api/brain/* routes."""
    rules = {r.rule for r in app_module.app.url_map.iter_rules()}
    assert "/api/brain/synthesis" in rules
    assert "/api/brain/correlate" in rules
    assert "/api/brain/history" in rules


def test_brain_synthesis_endpoint_returns_payload(client, app_module, monkeypatch):
    """Without persist=1 the endpoint must return health_score + narrative
    even when every BQ probe fails — the dashboard hero gauge depends on
    this never returning a non-200.
    """
    response = client.get("/api/brain/synthesis")
    assert response.status_code == 200
    body = response.get_json()
    # health_score is required for the gauge to render.
    assert "health_score" in body
    assert isinstance(body["health_score"], (int, float))
    assert "narrative" in body
    assert "priority_actions" in body
    assert "degraded_silos" in body


def test_brain_history_endpoint_returns_rows_shape(client):
    """Empty BQ table → endpoint still returns {"rows": []}, not 500."""
    response = client.get("/api/brain/history?limit=12")
    assert response.status_code == 200
    body = response.get_json()
    assert "rows" in body
    assert isinstance(body["rows"], list)


def test_brain_correlate_endpoint_returns_matches_shape(client):
    response = client.get("/api/brain/correlate")
    assert response.status_code == 200
    body = response.get_json()
    assert "matches" in body
    assert isinstance(body["matches"], list)
    assert "count" in body


def test_index_renders_brain_panel_in_terminal_tab():
    """The brain panel ships inside the cypherpunk terminal's Brain tab pane.
    Smoke-grep against the template file directly so we don't need to
    spin up the full Flask render path with a fake BQ client.
    """
    template_path = REPO_ROOT / "services" / "analytics_dashboard" / "templates" / "index.html"
    html = template_path.read_text(encoding="utf-8")

    # Marker 1: brain section and title exist.
    assert 'id="brain-section-h"' in html
    assert "Sapphire Brain" in html
    assert "cross-silo synthesis" in html

    # Marker 2: brain hero panel contains the composite gauge and narrative.
    assert '<div class="section-h" id="brain-section-h">' in html

    # Marker 3: public page routes privileged controls to the admin console.
    assert 'href="/admin"' in html
    assert "/api/brain/synthesis?persist=1" not in html
    assert "/api/brain/correlate" not in html

    # Marker 4: narrative, actions, and degraded element ids ship.
    assert 'id="brain-narrative"' in html
    assert 'id="brain-degraded"' in html
    assert 'id="brain-actions"' in html


def test_index_renders_project_tab_manifest():
    template_path = REPO_ROOT / "services" / "analytics_dashboard" / "templates" / "index.html"
    html = template_path.read_text(encoding="utf-8")

    assert "public systems" in html
    assert 'id="project-map"' in html
    assert "project_tabs" in html
    assert "Sapphire project tabs" not in html
    assert "Open THO Frontend" not in html  # rendered from data, not hard-coded drift


def test_index_renders_visible_public_console_refactor():
    template_path = REPO_ROOT / "services" / "analytics_dashboard" / "templates" / "index.html"
    html = template_path.read_text(encoding="utf-8")

    assert 'id="public-console"' in html
    assert "Sapphire OS is live, gated, and failover-aware." in html
    assert "Product routes, not internal telemetry." in html
    assert "/api/failover/readiness" in html
    assert 'id="console-lanes"' in html
    assert "raw service/device evidence" not in html


def test_index_markets_panel_distinguishes_partial_feed_from_total_outage():
    template_path = REPO_ROOT / "services" / "analytics_dashboard" / "templates" / "index.html"
    html = template_path.read_text(encoding="utf-8")

    assert "Global market totals loaded; showing trending assets" in html
    assert "Price list temporarily unavailable" in html
    assert "const trending = Array.isArray(data.trending)" in html


def test_index_onboarding_tour_is_help_invoked_not_auto_started():
    template_path = REPO_ROOT / "services" / "analytics_dashboard" / "templates" / "index.html"
    html = template_path.read_text(encoding="utf-8")

    assert "help-show-tour" in html
    assert "setTimeout(() => startTour(false)" not in html


def test_index_brain_panel_fetches_public_brain_summary_only():
    """The public brain data-loader hits synthesis only. Privileged
    history, persistence, and correlation endpoints stay out of the shell.
    """
    template_path = REPO_ROOT / "services" / "analytics_dashboard" / "templates" / "index.html"
    html = template_path.read_text(encoding="utf-8")
    assert "/api/brain/synthesis" in html
    assert "/api/brain/correlate" not in html
    assert "/api/brain/history" not in html


# ---------------------------------------------------------------------------
# Sapphire Brain — Gemini LLM augmentation (mocked, no Vertex calls)
# ---------------------------------------------------------------------------


def _stub_brain_module(app_module):
    """Convenience: return the live brain module loaded by app.py."""
    return sys.modules["brain"]


def _stub_brain_external_observations(brain, monkeypatch):
    """Keep LLM tests deterministic by removing live HTTP feed drift."""

    def _stable_json(url, timeout=3.0):
        if "tho.sapphirealpha.xyz" in url:
            return {"status": "ok", "warnings": []}
        return {"records": [], "fetched_at": "2026-05-02T00:00:00+00:00"}

    monkeypatch.setattr(brain, "_http_get_json", _stable_json)


def test_brain_synthesis_includes_narrative_llm_field(client, app_module, monkeypatch):
    """When LLM_BRAIN_ENABLED=1 and Vertex returns a string, narrative_llm
    must appear on the synthesis payload — the deterministic narrative
    field stays untouched.
    """
    brain = _stub_brain_module(app_module)
    _stub_brain_external_observations(brain, monkeypatch)
    monkeypatch.setattr(brain, "LLM_BRAIN_ENABLED", True)
    monkeypatch.setattr(
        brain,
        "_vertex_generate",
        lambda prompt: {
            "narrative": "Threat volume nominal; trading silent. Restart signal-logger.",
            "model": "gemini-2.0-flash-exp",
            "prompt_tokens": 220,
            "completion_tokens": 28,
            "latency_ms": 410,
        },
    )
    # Stomp the cache so we don't pick up a hit from a previous test.
    with brain._llm_cache_lock:
        brain._llm_cache.update({"key": None, "ts": 0.0, "value": None})

    response = client.get("/api/brain/synthesis")
    assert response.status_code == 200
    body = response.get_json()
    # Field is always present; non-null when Vertex returned a string.
    assert "narrative_llm" in body
    assert body["narrative_llm"] is not None
    assert "Threat volume" in body["narrative_llm"]
    # The deterministic narrative is still emitted untouched.
    assert isinstance(body.get("narrative"), str)
    assert body["narrative"]
    # llm_meta exposes the cache + token info for observability.
    assert isinstance(body.get("llm_meta"), dict)
    assert body["llm_meta"]["model"] == "gemini-2.0-flash-exp"


def test_brain_synthesis_narrative_llm_is_null_when_vertex_unavailable(
    client, app_module, monkeypatch
):
    """If Vertex import or call fails, narrative_llm must be None — the
    endpoint must NOT fail and the deterministic narrative must remain.
    """
    brain = _stub_brain_module(app_module)
    _stub_brain_external_observations(brain, monkeypatch)
    monkeypatch.setattr(brain, "LLM_BRAIN_ENABLED", True)
    monkeypatch.setattr(brain, "_vertex_generate", lambda prompt: None)
    with brain._llm_cache_lock:
        brain._llm_cache.update({"key": None, "ts": 0.0, "value": None})

    response = client.get("/api/brain/synthesis")
    assert response.status_code == 200
    body = response.get_json()
    assert body["narrative_llm"] is None
    assert isinstance(body["narrative"], str)


def test_brain_synthesis_skips_llm_when_disabled(client, app_module, monkeypatch):
    """LLM_BRAIN_ENABLED=0 should skip the Vertex hop entirely — no call,
    narrative_llm null.
    """
    brain = _stub_brain_module(app_module)
    _stub_brain_external_observations(brain, monkeypatch)
    monkeypatch.setattr(brain, "LLM_BRAIN_ENABLED", False)

    sentinel = {"called": False}

    def _boom(prompt):
        sentinel["called"] = True
        return {"narrative": "should not run", "model": "x"}

    monkeypatch.setattr(brain, "_vertex_generate", _boom)

    response = client.get("/api/brain/synthesis")
    assert response.status_code == 200
    body = response.get_json()
    assert body["narrative_llm"] is None
    assert sentinel["called"] is False


def test_brain_synthesis_caches_llm_result(client, app_module, monkeypatch):
    """Two back-to-back synthesis calls (same observation) must invoke
    Vertex at most once; the second is served from the in-process cache.
    """
    brain = _stub_brain_module(app_module)
    _stub_brain_external_observations(brain, monkeypatch)
    monkeypatch.setattr(brain, "LLM_BRAIN_ENABLED", True)

    counter = {"n": 0}

    def _gen(prompt):
        counter["n"] += 1
        return {
            "narrative": f"call number {counter['n']}",
            "model": "gemini-2.0-flash-exp",
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "latency_ms": 200,
        }

    monkeypatch.setattr(brain, "_vertex_generate", _gen)
    with brain._llm_cache_lock:
        brain._llm_cache.update({"key": None, "ts": 0.0, "value": None})

    r1 = client.get("/api/brain/synthesis")
    r2 = client.get("/api/brain/synthesis")
    assert r1.status_code == 200 and r2.status_code == 200
    # Both responses carry a narrative_llm but generate_content fired once.
    assert counter["n"] == 1
    assert r1.get_json()["narrative_llm"] == r2.get_json()["narrative_llm"]
    # Second response carries cached=True.
    assert r2.get_json()["llm_meta"]["cached"] is True


def test_brain_llm_refresh_endpoint_bypasses_cache(client, app_module, monkeypatch):
    """POST /api/brain/llm-refresh must force a fresh Vertex call even
    when the cache is warm.
    """
    brain = _stub_brain_module(app_module)
    _stub_brain_external_observations(brain, monkeypatch)
    monkeypatch.setattr(brain, "LLM_BRAIN_ENABLED", True)

    counter = {"n": 0}

    def _gen(prompt):
        counter["n"] += 1
        return {
            "narrative": f"refresh-{counter['n']}",
            "model": "gemini-2.0-flash-exp",
            "prompt_tokens": 100,
            "completion_tokens": 5,
            "latency_ms": 180,
        }

    monkeypatch.setattr(brain, "_vertex_generate", _gen)
    with brain._llm_cache_lock:
        brain._llm_cache.update({"key": None, "ts": 0.0, "value": None})

    # Warm the cache via the GET endpoint.
    client.get("/api/brain/synthesis")
    assert counter["n"] == 1

    # llm-refresh must bypass.
    r = client.post("/api/brain/llm-refresh")
    assert r.status_code == 200
    assert counter["n"] == 2
    assert r.get_json()["narrative_llm"] == "refresh-2"
    assert r.get_json()["llm_meta"]["cached"] is False


def test_brain_llm_refresh_endpoint_is_registered(app_module):
    """The new POST /api/brain/llm-refresh route must show up in the URL map."""
    rules = {(r.rule, frozenset(r.methods or set())) for r in app_module.app.url_map.iter_rules()}
    matched = [rule for rule, methods in rules if rule == "/api/brain/llm-refresh"]
    assert matched, "expected /api/brain/llm-refresh in url_map"


def test_brain_snapshot_drops_unknown_silo_fields(app_module):
    """Defense-in-depth: ``_snapshot_for_llm`` is a whitelist — even if a
    silo dict gains a sensitive key (e.g. ``api_key_demo``) the key is
    dropped before the snapshot is sent to Gemini.
    """
    brain = _stub_brain_module(app_module)
    obs = {
        "ts": "2026-05-02T00:00:00+00:00",
        "silos": {
            "trading": {"signals_24h": 1, "api_key_demo": "leaked"},
            "regime": {"latest_valid": None, "latest_any": None},
            "threat": {"new_24h": 0, "critical_24h": 0, "total": 0},
            "services": [],
            "inference": {"calls": 0, "errors": 0},
            "tho": {"status": "ok"},
            "threat_live": {"records_now": 0},
        },
    }
    snap = brain._snapshot_for_llm(obs)
    serialized = repr(snap)
    assert "leaked" not in serialized
    assert "api_key_demo" not in serialized


def test_brain_blocklist_triggers_on_sensitive_serialization(app_module):
    """``_has_sensitive_data`` matches every term in the blocklist —
    api_key / secret / password / token / jwt / ssn / credit_card."""
    brain = _stub_brain_module(app_module)
    for term in (
        "api_key",
        "api-key",
        "secret",
        "password",
        "TOKEN",
        "jwt",
        "ssn",
        "credit_card",
        "credit-card",
    ):
        assert brain._has_sensitive_data(f"value contains {term} here") is True
    # Clean strings pass through.
    assert brain._has_sensitive_data("calls=1234 errors=2") is False


def test_brain_synthesize_llm_short_circuits_on_blocklist_hit(app_module, monkeypatch):
    """If ``_has_sensitive_data`` triggers, _synthesize_llm returns None
    without ever calling Vertex.
    """
    brain = _stub_brain_module(app_module)
    monkeypatch.setattr(brain, "LLM_BRAIN_ENABLED", True)
    monkeypatch.setattr(brain, "_has_sensitive_data", lambda blob: True)

    sentinel = {"called": False}

    def _gen(prompt):
        sentinel["called"] = True
        return {"narrative": "leaked", "model": "x"}

    monkeypatch.setattr(brain, "_vertex_generate", _gen)

    result = brain._synthesize_llm({"ts": "t", "silos": {}})
    assert result is None
    assert sentinel["called"] is False
