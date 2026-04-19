"""Dashboard endpoint smoke tests.

Asserts the de-staled endpoints return the new shape and that /metrics
records latency for subsequent requests.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "services" / "dashboard"
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))


_AUTH = "Basic " + base64.b64encode(b"sapphire:test").decode()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    os.environ["AUTH_PASSWORD"] = "test"
    # Re-import app fresh for each test to reset in-process metrics state
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as dash_app  # type: ignore

    # Point stale-data endpoints at tmp JSONL to isolate fixtures
    monkeypatch.setattr(
        dash_app, "_cache", {}
    )
    monkeypatch.setattr(
        dash_app, "_cache_time", {}
    )

    client = dash_app.app.test_client()
    return dash_app, client


def test_metrics_endpoint_requires_auth(app_client):
    _, client = app_client
    r = client.get("/metrics")
    assert r.status_code == 401


def test_metrics_records_latency(app_client):
    dash_app, client = app_client
    # Warm up with an auth'd call
    client.get("/health", headers={"Authorization": _AUTH})
    r = client.get("/metrics", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert "routes" in body
    assert body["window_samples"] > 0
    # X-Response-Time-ms header present on latest response
    assert "X-Response-Time-ms" in r.headers


def test_opportunities_reads_signals_jsonl(app_client, tmp_path, monkeypatch):
    dash_app, client = app_client
    # Redirect the Sapphire data root for this test
    fake_signals = tmp_path / "trading_signals.jsonl"
    fake_signals.parent.mkdir(exist_ok=True)
    fake_signals.write_text(json.dumps({
        "timestamp": "2026-04-17T10:00:00+00:00",
        "symbol": "BTCUSDT", "action": "BUY", "price": 68000.0,
        "confidence": 0.82, "strategy": "ensemble",
        "raw": {"reason": "3F ensemble: MA↑ MACD↑ Vol↑",
                "edge": 0.03, "kelly_size_pct": 1.5},
    }) + "\n" + json.dumps({
        "timestamp": "2026-04-17T10:30:00+00:00",
        "symbol": "ETHUSDT", "action": "SELL", "price": 3100.0,
        "confidence": 0.35, "strategy": "rsi_top",  # below threshold
    }) + "\n")

    # Monkeypatch Path.home so the endpoint's os-agnostic lookup hits our tmp
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # Recreate the signals path under tmp_path per the endpoint's layout
    target = tmp_path / "Code" / "Sapphire" / "data"
    target.mkdir(parents=True)
    (target / "trading_signals.jsonl").write_text(fake_signals.read_text())

    r = client.get("/api/opportunities", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    ops = body["opportunities"]
    # Only the BTC one (conf 0.82) meets the 0.5 threshold
    assert len(ops) == 1
    assert ops[0]["symbol"] == "BTCUSDT"
    assert ops[0]["side"] == "buy"
    assert ops[0]["confidence"] == 0.82
    assert ops[0]["edge"] == 0.03


def test_logs_endpoint_returns_shape(app_client):
    _, client = app_client
    r = client.get("/api/logs?hours=24", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert "logs" in body
    assert "count" in body
    assert "timestamp" in body
    assert isinstance(body["logs"], list)


def test_logs_filter_by_level_and_service(app_client, tmp_path, monkeypatch):
    _, client = app_client
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    data_dir = tmp_path / "Code" / "Sapphire" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "system_events.jsonl").write_text("\n".join([
        json.dumps({
            "timestamp": "2099-01-01T00:00:00+00:00",  # always in-window
            "type": "signal.received",
            "message": "BUY BTC",
            "tags": ["type:trading", "priority:p1"],
        }),
        json.dumps({
            "timestamp": "2099-01-01T00:00:00+00:00",
            "type": "heartbeat",
            "message": "ok",
            "tags": ["priority:p2"],
        }),
    ]) + "\n")

    r = client.get("/api/logs?hours=168&level=WARN",
                   headers={"Authorization": _AUTH})
    body = r.get_json()
    assert all(e["level"] == "WARN" for e in body["logs"])

    r = client.get("/api/logs?hours=168&service=signal",
                   headers={"Authorization": _AUTH})
    body = r.get_json()
    assert all("signal" in e["type"] for e in body["logs"])


def test_foundry_readiness_reports_data_ready(app_client, tmp_path, monkeypatch):
    _, client = app_client
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    data_dir = tmp_path / "Code" / "Sapphire" / "data"
    (data_dir / "health").mkdir(parents=True)
    (data_dir / "metrics").mkdir(parents=True)
    (data_dir / "intelligence" / "2026-04-19").mkdir(parents=True)
    (data_dir / "system_events.jsonl").write_text('{"type":"test"}\n')
    (data_dir / "health" / "2026-04-19.ndjson").write_text('{"service":"dashboard"}\n')
    (data_dir / "metrics" / "2026-04-19.ndjson").write_text('{"metric":"latency"}\n')
    (data_dir / "trading_predictions.jsonl").write_text('{"symbol":"BTC"}\n')
    (data_dir / "intelligence" / "2026-04-19" / "predictions.json").write_text(
        json.dumps({"predictions": {"BTC-USD": {"direction": "bullish"}}})
    )

    r = client.get("/api/foundry/readiness", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "partial"
    assert body["badge"] == "DATA READY"
    assert body["auth_mode"] == "not-configured"
    assert body["totals"]["files"] >= 4
    groups = {group["id"]: group for group in body["dataset_groups"]}
    assert groups["system-events"]["files"] == 1
    assert groups["ops-telemetry"]["files"] >= 2
    assert groups["market-forecasts"]["files"] >= 2


def test_intel_sources_include_foundry_readiness(app_client, tmp_path, monkeypatch):
    _, client = app_client
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    data_dir = tmp_path / "Code" / "Sapphire" / "data"
    intel_day = data_dir / "intelligence" / "2026-04-19"
    intel_day.mkdir(parents=True)
    (data_dir / "system_events.jsonl").write_text('{"type":"test"}\n')
    (intel_day / "threats.json").write_text(
        json.dumps(
            {
                "threats": [
                    {
                        "id": "threat-1",
                        "title": "APT test cluster",
                        "score": 9,
                        "published": "2026-04-19T02:00:00Z",
                        "source": "unit-test",
                    }
                ]
            }
        )
    )

    r = client.get("/api/intel", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["items"][0]["title"] == "APT test cluster"
    sources = {source["name"]: source for source in body["sources"]}
    assert sources["Threat snapshots"]["status"] == "active"
    assert sources["Threat snapshots"]["items"] == 1
    assert sources["Palantir Foundry"]["status"] == "partial"
    assert sources["Palantir Foundry"]["items"] >= 1
