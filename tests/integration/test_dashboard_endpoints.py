"""Dashboard endpoint smoke tests.

Asserts the de-staled endpoints return the new shape and that /metrics
records latency for subsequent requests.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import zipfile
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


def test_market_universe_endpoint_uses_strategy_lab(app_client, monkeypatch):
    _, client = app_client
    from lib.trading import strategy_lab

    monkeypatch.setattr(
        strategy_lab,
        "build_market_universe",
        lambda fetch_live=True: {
            "generated_at": "2026-04-27T00:00:00+00:00",
            "stale": False,
            "liked_tokens": [{"symbol": "BTC", "tradingview_symbol": "BINANCE:BTCUSDT"}],
            "trending_tokens": [{"symbol": "AAVE", "source": "coingecko_trending"}],
            "venue_matrix": [{"symbol": "BTC", "tradingview": "BINANCE:BTCUSDT"}],
            "corrected_aliases": {"MATIC": "POL"},
        },
    )

    r = client.get("/api/analytics/market-universe", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["liked_tokens"][0]["symbol"] == "BTC"
    assert body["trending_tokens"][0]["symbol"] == "AAVE"
    assert body["corrected_aliases"]["MATIC"] == "POL"


def test_order_draft_endpoint_is_dry_run(app_client):
    _, client = app_client

    r = client.post(
        "/api/trading/order-draft",
        headers={"Authorization": _AUTH},
        json={"symbol": "BTCUSDT", "action": "buy", "notional_usd": 50},
    )

    assert r.status_code == 200
    body = r.get_json()
    assert body["execution_enabled"] is False
    assert all(draft["execution_enabled"] is False for draft in body["drafts"])
    assert {draft["venue"] for draft in body["drafts"]} >= {"paper", "hyperliquid"}


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
    assert body["schema_audit"]["status"] in {"empty", "ready", "schema_warning"}
    assert "sync_history_readback" in body["schema_audit"]


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


def test_investment_intel_endpoint_returns_source_mesh(app_client, tmp_path, monkeypatch):
    _, client = app_client
    pack_path = tmp_path / "investment.zip"
    with zipfile.ZipFile(pack_path, "w") as zf:
        zf.writestr(
            "investment_research.agent.final.md",
            "\n".join(
                [
                    "# Asymmetric Bets 2026",
                    "## Top 10 Conviction Ideas",
                    "| # | Ticker | Company | Risk Tier | Price Target | Implied Upside | Key Catalyst |",
                    "|---|--------|---------|-----------|-------------|----------------|--------------|",
                    "| 1 | BWXT | BWX Technologies | Moderate | 250 | +20% | Nuclear demand |",
                    "Principle: multi-theme premium plus source freshness.",
                ]
            ),
        )
        zf.writestr(
            "BWXT_info.csv",
            "symbol,longName,sectorDisp,industryDisp,currentPrice\n"
            "BWXT,BWX Technologies Inc.,Industrials,Aerospace & Defense,223.15\n",
        )
    monkeypatch.setenv("SAPPHIRE_INVESTMENT_RESEARCH_ZIP", str(pack_path))

    r = client.get("/api/investments/intel", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "read-only"
    assert body["research_pack"]["available"] is True
    assert body["source_mesh"]["totals"]["connectors"] >= 8
    symbols = {asset["symbol"]: asset for asset in body["universe"]}
    assert "BWXT" in symbols
    assert "BTC" in symbols
    assert "sec_companyfacts" in symbols["BWXT"]["connectors"]
    assert "hyperliquid_info" in symbols["BTC"]["connectors"]
    assert body["crypto_bridge"]["live_requested"] is False
    assert {row["symbol"] for row in body["crypto_bridge"]["tokens_we_like"]} >= {"BTC", "HYPE"}
    assert body["source_probes"]["summary"]["total"] >= 8
    assert body["materialization_plan"]["total_rows"] > len(body["universe"])
    assert body["series_catalog"]


def test_investment_sources_endpoint_returns_robinhood_presence(app_client):
    _, client = app_client
    r = client.get("/api/investments/sources", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "read-only"
    assert "source_mesh" in body
    assert body["robinhood"]["mode"] == "read-only portfolio snapshot"


def test_investment_probes_endpoint_is_non_live_by_default(app_client):
    _, client = app_client
    r = client.get("/api/investments/probes", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "read-only"
    assert body["live_requested"] is False
    probes = {row["id"]: row for row in body["probes"]}
    assert probes["sec_company_tickers"]["status"] == "not_requested"
    assert body["series_catalog"]


def test_sovereign_thesis_endpoint_is_research_only(app_client):
    _, client = app_client
    r = client.get("/api/investments/thesis", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "research_intel_only"
    assert body["safety"]["live_trading_enabled"] is False
    assert body["safety"]["execution_enabled"] is False
    assert body["totals"]["assets"] >= 30
    assert body["totals"]["lenses"] >= 14
    assert body["totals"]["evidence_required"] >= 400
    assert body["totals"]["evidence_needs_wiring"] >= 1
    assert body["evidence_summary"]["wired_pct"] >= body["evidence_summary"]["coverage_pct"]
    assert body["materialization_plan"]["writes_by_default"] is False
    assert body["materialization_plan"]["total_rows"] > len(body["assets"])
    rows = {row["symbol"]: row for row in body["assets"]}
    assert body["assets"][0]["symbol"] == "ETH"
    assert rows["ETH"]["fit"] == "core"
    assert rows["BTC"]["fit"] == "aligned"
    assert "hard_money" in rows["BTC"]["aligned_lenses"]
    assert "eth_economic_zone" in rows["ETH"]["aligned_lenses"]
    assert "ethereum:privacy_cluster" in {row["source_id"] for row in rows["ETH"]["evidence_ledger"]}
    assert rows["BTC"]["evidence_ledger"]
    assert "BWXT" in rows
    assert {"AAVE", "UNI", "ENS", "ARB", "OP"} <= set(rows)
    assert body["ops_queue"]
    assert any(row["status"] == "needs_wiring" for row in body["evidence_ledger"])


def test_continuous_intelligence_endpoint_is_dry_run(app_client):
    _, client = app_client
    r = client.get("/api/autonomy/continuous-intelligence", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "read_only_task_planning"
    assert body["execution_enabled"] is False
    assert body["live_trading_enabled"] is False
    assert body["telegram_sends_enabled"] is False
    assert body["writes_by_default"] is False
    assert body["tasks"]
    assert body["next_dispatch"]
    assert {task["lane"] for task in body["tasks"]} >= {
        "strategy_backtest",
        "confluence_scan",
        "thesis_research",
    }
    assert any(target["id"] == "windows-gpu" for target in body["runtime_targets"])


def test_continuous_intelligence_artifacts_endpoint_is_read_only(app_client):
    _, client = app_client
    r = client.get("/api/autonomy/continuous-intelligence/artifacts", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "continuous_intelligence_artifact_status"
    assert body["write_enabled"] is False
    assert body["writes_by_default"] is False
    assert body["execution_enabled"] is False
    assert body["live_trading_enabled"] is False
    assert body["telegram_sends_enabled"] is False
    assert body["snapshot_preview"]["write_enabled"] is False
    assert body["snapshot_preview"]["records"] >= 10


def test_continuous_intelligence_lease_preview_is_dry_run(app_client):
    _, client = app_client
    r = client.get(
        "/api/autonomy/continuous-intelligence/lease-preview"
        "?agent_id=windows-gpu&target_runtime=windows-gpu&limit=2",
        headers={"Authorization": _AUTH},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "dry_run_task_lease"
    assert body["write_enabled"] is False
    assert body["writes_by_default"] is False
    assert body["safety"]["dry_run_dispatch_only"] is True
    assert body["safety"]["execution_enabled"] is False
    assert body["safety"]["telegram_sends_enabled"] is False
    assert body["leased_count"] >= 1
    assert all(lease["target_runtime"] == "windows-gpu" for lease in body["leases"])


def test_sovereign_thesis_page_renders(app_client):
    _, client = app_client
    r = client.get("/sovereign-thesis", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Sovereign Thesis" in html
    assert "Evidence Ledger" in html
    assert "Materialization Plan" in html
    assert "/api/investments/thesis" in html
