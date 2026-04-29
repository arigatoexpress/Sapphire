"""Dashboard endpoint smoke tests.

Asserts the de-staled endpoints return the new shape and that /metrics
records latency for subsequent requests.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "services" / "dashboard"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("flask") is None,
    reason="dashboard endpoint integration tests require Flask",
)


def _prioritize_dashboard_path() -> None:
    dashboard_path = str(DASHBOARD)
    while dashboard_path in sys.path:
        sys.path.remove(dashboard_path)
    sys.path.insert(0, dashboard_path)


_prioritize_dashboard_path()


_AUTH = "Basic " + base64.b64encode(b"sapphire:test").decode()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    os.environ["AUTH_PASSWORD"] = "test"
    # Re-import app fresh for each test to reset in-process metrics state
    if "app" in sys.modules:
        del sys.modules["app"]
    _prioritize_dashboard_path()
    import app as dash_app  # type: ignore

    # Point stale-data endpoints at tmp JSONL to isolate fixtures
    monkeypatch.setattr(dash_app, "_cache", {})
    monkeypatch.setattr(dash_app, "_cache_time", {})

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


def test_system_api_normalizes_inference_tiers(app_client, monkeypatch):
    dash_app, client = app_client

    def fake_fetch(url: str):
        if url.endswith("/health"):
            return {
                "status": "ok",
                "endpoints": {
                    "windows-gpu": "healthy",
                    "pi-rari1": "failed",
                    "pi-rari2": "failed",
                    "mac-local": "healthy",
                    "kimi-cloud": "healthy",
                },
                "tiers": {
                    "t1_windows_gpu": "http://100.71.10.48:11434",
                    "t2_pi_rari1": "http://100.120.191.1:11434 (enabled=True)",
                    "t2_pi_rari2": "http://100.87.225.89:11434 (enabled=True)",
                    "t3_mac_local": "http://127.0.0.1:11434",
                    "t4_kimi_cloud": "https://api.moonshot.cn/v1",
                },
            }
        if url.endswith("/metrics"):
            return {"metrics": {}}
        if url.endswith("/json"):
            return []
        if url.endswith("/api/signals/recent"):
            return {"count": 0, "signals": []}
        return {"status": "ok"}

    class _Socket:
        def close(self):
            return None

    monkeypatch.setattr(dash_app, "fetch_sync", fake_fetch)
    import socket

    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: _Socket())

    response = client.get("/api/system", headers={"Authorization": _AUTH})

    assert response.status_code == 200
    body = response.get_json()
    tiers = body["inference"]["tiers"]
    assert tiers["t1"]["healthy"] is True
    assert tiers["t1"]["endpoint_key"] == "windows-gpu"
    assert tiers["t1"]["url"] == "http://100.71.10.48:11434"
    assert tiers["t2a"]["healthy"] is False
    assert body["inference"]["endpoints"]["windows-gpu"] == "healthy"
    assert body["inference"]["raw_tiers"]["t1_windows_gpu"] == "http://100.71.10.48:11434"


def test_opportunities_reads_signals_jsonl(app_client, tmp_path, monkeypatch):
    dash_app, client = app_client
    # Redirect the Sapphire data root for this test
    fake_signals = tmp_path / "trading_signals.jsonl"
    fake_signals.parent.mkdir(exist_ok=True)
    fake_signals.write_text(
        json.dumps(
            {
                "timestamp": "2026-04-17T10:00:00+00:00",
                "symbol": "BTCUSDT",
                "action": "BUY",
                "price": 68000.0,
                "confidence": 0.82,
                "strategy": "ensemble",
                "raw": {
                    "reason": "3F ensemble: MA↑ MACD↑ Vol↑",
                    "edge": 0.03,
                    "kelly_size_pct": 1.5,
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "timestamp": "2026-04-17T10:30:00+00:00",
                "symbol": "ETHUSDT",
                "action": "SELL",
                "price": 3100.0,
                "confidence": 0.35,
                "strategy": "rsi_top",  # below threshold
            }
        )
        + "\n"
    )

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


def test_sentinel_demo_endpoint_is_testnet_paper_only(app_client):
    _, client = app_client

    r = client.get("/api/hackathon/sentinel/demo", headers={"Authorization": _AUTH})

    assert r.status_code == 200
    body = r.get_json()
    assert body["project"]["primary_chain"] == "Robinhood Chain Testnet"
    assert body["project"]["mode"] == "testnet_paper_only"
    assert body["approved_flow"]["approved"] is True
    assert body["blocked_flow"]["approved"] is False
    assert body["safety"]["live_trading_enabled"] is False
    assert body["safety"]["real_funds_enabled"] is False


def test_sentinel_page_renders(app_client):
    _, client = app_client

    r = client.get("/chain/sentinel", headers={"Authorization": _AUTH})

    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Sapphire Sentinel" in html
    assert "/api/hackathon/sentinel/demo" in html


def test_sentinel_evaluate_endpoint_blocks_untrusted_domain(app_client):
    _, client = app_client

    r = client.post(
        "/api/hackathon/sentinel/evaluate",
        headers={"Authorization": _AUTH},
        json={
            "resource": "https://untrusted.example/api/alpha",
            "amount_usdc": "0.01",
            "action": "buy-private-signal",
            "payload_summary": "normal request",
        },
    )

    assert r.status_code == 200
    body = r.get_json()
    assert body["execution_enabled"] is False
    assert body["mode"] == "policy_preview_only"
    assert body["decision"]["approved"] is False
    assert "domain_not_allowed" in body["decision"]["risk_flags"]


def test_trading_shadow_controller_endpoint_is_paper_only(app_client, monkeypatch):
    _, client = app_client
    from lib.trading import shadow_controller

    monkeypatch.setattr(
        shadow_controller,
        "build_shadow_trading_report",
        lambda fetch_live=True: {
            "mode": "paper_shadow",
            "live_execution_enabled": False,
            "paper_trading_enabled": True,
            "candidates": [],
            "risk_policy": {"bounded_candidate_notional_usd": 5.0},
        },
    )

    r = client.get("/api/trading/shadow-controller?offline=1", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "paper_shadow"
    assert body["live_execution_enabled"] is False
    assert body["risk_policy"]["bounded_candidate_notional_usd"] == 5.0


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
    (data_dir / "system_events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2099-01-01T00:00:00+00:00",  # always in-window
                        "type": "signal.received",
                        "message": "BUY BTC",
                        "tags": ["type:trading", "priority:p1"],
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2099-01-01T00:00:00+00:00",
                        "type": "heartbeat",
                        "message": "ok",
                        "tags": ["priority:p2"],
                    }
                ),
            ]
        )
        + "\n"
    )

    r = client.get("/api/logs?hours=168&level=WARN", headers={"Authorization": _AUTH})
    body = r.get_json()
    assert all(e["level"] == "WARN" for e in body["logs"])

    r = client.get("/api/logs?hours=168&service=signal", headers={"Authorization": _AUTH})
    body = r.get_json()
    assert all("signal" in e["type"] for e in body["logs"])


def test_foundry_readiness_reports_data_ready(app_client, tmp_path, monkeypatch):
    _, client = app_client
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    repo_root = tmp_path / "Code" / "Sapphire"
    monkeypatch.setenv("SAPPHIRE_REPO_ROOT", str(repo_root))
    data_dir = repo_root / "data"
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
    assert "ethereum:privacy_cluster" in {
        row["source_id"] for row in rows["ETH"]["evidence_ledger"]
    }
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
    r = client.get(
        "/api/autonomy/continuous-intelligence/artifacts", headers={"Authorization": _AUTH}
    )
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
    assert "Continuous Intelligence" in html
    assert "Artifact Lease Preview" in html
    assert "/api/investments/thesis" in html
    assert "/api/autonomy/continuous-intelligence" in html
    assert "/api/autonomy/continuous-intelligence/artifacts" in html
    assert "/api/autonomy/continuous-intelligence/lease-preview" in html
    assert "Gemini OODA (dry-run)" in html
    assert "/api/gemini-ooda" in html
    assert "Daily Delta" in html


def test_gemini_ooda_endpoint_is_dry_run_dashboard(app_client):
    _, client = app_client
    r = client.get("/api/gemini-ooda", headers={"Authorization": _AUTH})
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "gemini_ooda_dry_run_dashboard"
    assert body["safety"]["execution_enabled"] is False
    assert body["safety"]["live_trading_enabled"] is False
    assert body["safety"]["telegram_sends_enabled"] is False
    assert body["safety"]["writes_by_default"] is False
    assert "dashboard_endpoint_dry_run_only" in body["safety"]["guards"]
    assert body["topic"]
    synthesis = body.get("synthesis") or {}
    assert synthesis
    assert "ooda" in synthesis
    metadata = synthesis.get("metadata") or {}
    # Endpoint always requests dry-run; live mode requires the env-gated tool path.
    assert metadata.get("mode_actual") in {
        "dry-run",
        "dry-run-blocked-by-env",
        "dry-run-safety",
    }
    status = body.get("tool_status") or {}
    assert status.get("max_calls_per_hour") == 8
    assert status.get("max_tokens_per_month") == 500_000


def test_gemini_ooda_endpoint_accepts_topic_override(app_client):
    _, client = app_client
    r = client.get(
        "/api/gemini-ooda?topic=Probe%20OODA%20override&context=paste-safe%20context%20block",
        headers={"Authorization": _AUTH},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["topic"] == "Probe OODA override"
    assert body["context_summary_chars"] == len("paste-safe context block")


def test_narrative_eval_page_and_endpoints_render_empty_state(app_client):
    _, client = app_client
    page = client.get("/narrative-eval", headers={"Authorization": _AUTH})
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Narrative Eval" in html
    assert "/api/narrative-eval-summary" in html
    assert "/api/narrative-eval-aggregates" in html

    summary = client.get("/api/narrative-eval-summary", headers={"Authorization": _AUTH})
    assert summary.status_code == 200
    body = summary.get_json()
    assert body["ok"] is True
    assert body["overall"]["scored"] == 0

    aggregates = client.get("/api/narrative-eval-aggregates?group_by=symbol", headers={"Authorization": _AUTH})
    assert aggregates.status_code == 200
    assert aggregates.get_json()["groups"] == {}

    diagnostics = client.get("/api/narrative-eval-aggregates?view=diagnostics", headers={"Authorization": _AUTH})
    assert diagnostics.status_code == 200
    assert diagnostics.get_json()["false_positives"] == []


def test_gemini_ooda_endpoint_can_return_daily_diff(app_client, tmp_path, monkeypatch):
    dash_app, client = app_client
    packet_dir = tmp_path / "gemini-ooda"
    packet_dir.mkdir()
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    (packet_dir / f"{yesterday.isoformat()}.json").write_text(
        json.dumps(
            {
                "topic": "Sapphire daily thesis OODA snapshot",
                "context_summary": {"totals": {"assets": 2}},
                "tool_response": {"ooda": {"decide": "hold"}},
            }
        ),
        encoding="utf-8",
    )
    (packet_dir / f"{today.isoformat()}.json").write_text(
        json.dumps(
            {
                "topic": "Sapphire daily thesis OODA snapshot",
                "context_summary": {"totals": {"assets": 3}},
                "tool_response": {"ooda": {"decide": "watch deltas"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash_app, "_GEMINI_OODA_DAILY_DIR", packet_dir)

    r = client.get("/api/gemini-ooda?diff=1", headers={"Authorization": _AUTH})

    assert r.status_code == 200
    body = r.get_json()
    assert body["daily_diff"]["available"] is True
    mutated = {row["key"]: row for row in body["daily_diff"]["mutated"]}
    assert mutated["context_summary.totals.assets"]["before"] == "2"
    assert mutated["context_summary.totals.assets"]["after"] == "3"
    assert mutated["tool_response.ooda.decide"]["after"] == "watch deltas"
