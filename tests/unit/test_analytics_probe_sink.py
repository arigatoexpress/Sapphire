"""Tests for analytics dashboard public probe handling."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_analytics_app(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module_path = root / "services" / "analytics_dashboard" / "app.py"

    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_bigquery.Client = lambda project: object()
    fake_bigquery.QueryJobConfig = lambda query_parameters=None: types.SimpleNamespace(
        query_parameters=query_parameters or []
    )
    fake_bigquery.ScalarQueryParameter = lambda name, kind, value: types.SimpleNamespace(
        name=name,
        kind=kind,
        value=value,
    )
    fake_cloud.bigquery = fake_bigquery

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("BQ_DATASET", "test_dataset")

    spec = importlib.util.spec_from_file_location("analytics_dashboard_app_test", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.app.test_client()


def test_known_public_probes_return_no_content(monkeypatch):
    client = _load_analytics_app(monkeypatch)

    for path in (
        "/.git/config",
        "/feed/",
        "/wp-admin/install.php?step=1",
        "/wp-includes/ID3/license.txt",
    ):
        response = client.get(path)
        assert response.status_code == 204
        assert response.text == ""
        assert response.headers["Cache-Control"] == "no-store"


def test_wordpress_manifest_probe_suffix_returns_no_content(monkeypatch):
    client = _load_analytics_app(monkeypatch)

    response = client.get("/blog/wp-includes/wlwmanifest.xml")

    assert response.status_code == 204
    assert response.text == ""


def test_xmlrpc_post_probe_returns_no_content(monkeypatch):
    client = _load_analytics_app(monkeypatch)

    response = client.post("/xmlrpc.php", data="<methodCall />")

    assert response.status_code == 204
    assert response.text == ""


def test_unknown_path_stays_not_found(monkeypatch):
    client = _load_analytics_app(monkeypatch)

    response = client.get("/definitely-not-a-real-route")

    assert response.status_code == 404


def test_health_route_still_wins_over_probe_sink(monkeypatch):
    client = _load_analytics_app(monkeypatch)

    response = client.get("/healthz/")

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
