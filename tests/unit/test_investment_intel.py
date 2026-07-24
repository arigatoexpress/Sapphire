from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from lib.chain import sources
from lib.intel import investment_intel as intel


def _write_research_zip(path: Path) -> None:
    markdown = """# Asymmetric Bets 2026

## Top 10 Conviction Ideas

| # | Ticker | Company | Risk Tier | Price Target | Implied Upside | Key Catalyst |
|---|--------|---------|-----------|-------------|----------------|--------------|
| 1 | BWXT | BWX Technologies | Moderate | 250 | +20% | Nuclear demand |
| 2 | HYPE | Hyperliquid | Aggressive | n/a | n/a | Venue growth |

## Portfolio Construction Principles

Principle 1: The multi-theme premium is durable and justified by diverse demand.
Principle 2: Picks & shovels over platforms reduces binary platform risk.
Position sizing must keep speculative names small through drawdowns.
Quarterly catalyst reviews should track counter-arguments and source freshness.
"""
    csv_text = (
        "symbol,longName,sectorDisp,industryDisp,currentPrice,targetMeanPrice,"
        "recommendationKey,marketCap,totalRevenue,grossMargins\n"
        "BWXT,BWX Technologies Inc.,Industrials,Aerospace & Defense,223.15,"
        "234.54,buy,20443199488,3198425088,0.22913\n"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("investment_research.agent.final.md", markdown)
        zf.writestr("BWXT_info.csv", csv_text)


def test_load_research_pack_extracts_markdown_and_csv(tmp_path):
    pack_path = tmp_path / "research.zip"
    _write_research_zip(pack_path)

    pack = intel.load_research_pack(pack_path)

    assert pack.available is True
    assert pack.source_label == "research.zip"
    assert any(section["title"] == "Top 10 Conviction Ideas" for section in pack.sections)
    assert pack.top_ideas[0]["ticker"] == "BWXT"
    assert pack.csv_assets[0]["symbol"] == "BWXT"
    assert pack.csv_assets[0]["current_price"] == pytest.approx(223.15)
    assert any("multi-theme" in item.lower() for item in pack.mindset_principles)


def test_build_report_includes_equity_and_crypto_source_mesh(tmp_path):
    pack_path = tmp_path / "research.zip"
    _write_research_zip(pack_path)

    report = intel.build_investment_intel_report(pack_path)
    symbols = {asset["symbol"]: asset for asset in report["universe"]}
    connectors = {row["id"]: row for row in report["source_mesh"]["connectors"]}

    assert "BWXT" in symbols
    assert "BTC" in symbols
    assert "sec_companyfacts" in symbols["BWXT"]["connectors"]
    assert "hyperliquid_info" in symbols["BTC"]["connectors"]
    assert connectors["sec_submissions"]["status"] == "ready"
    assert connectors["fred_macro"]["status"] in {"ready", "needs_key"}
    assert report["mode"] == "read-only"
    assert "not financial advice" in report["disclaimer"].lower()
    assert any(row["id"] == "crypto-source-bridge" for row in report["ops_queue"])
    assert {row["symbol"] for row in report["crypto_bridge"]["tokens_we_like"]} >= {"BTC", "HYPE"}
    assert report["crypto_bridge"]["live_requested"] is False
    assert report["source_probes"]["summary"]["total"] >= 8
    assert report["series_catalog"]
    assert report["materialization_plan"]["total_rows"] > len(report["universe"])


def test_crypto_bridge_can_fetch_live_coingecko_snapshot(monkeypatch):
    monkeypatch.setattr(
        sources.CoinGeckoClient,
        "simple_prices",
        lambda _self, coin_ids: {coin_id: {"usd": 1.0} for coin_id in coin_ids},
    )
    monkeypatch.setattr(
        sources.CoinGeckoClient,
        "trending",
        lambda _self, limit=10: [
            sources.TrendingCoin(
                coin_id="hyperliquid",
                symbol="HYPE",
                name="Hyperliquid",
                market_cap_rank=15,
                score=0,
            )
        ],
    )
    universe = intel.build_universe()

    bridge = intel.build_crypto_bridge(universe, fetch_live=True)

    assert bridge["live_requested"] is True
    assert bridge["prices"]["BTC"]["usd"] == 1.0
    assert bridge["trending"][0]["symbol"] == "HYPE"
    assert bridge["errors"] == {}


def test_source_report_sanitizes_robinhood_to_presence_only(tmp_path, monkeypatch):
    secret_dir = tmp_path / ".config" / "sapphire-secrets"
    secret_dir.mkdir(parents=True)
    (secret_dir / "robinhood_api_key").write_text("secret-key")
    (secret_dir / "robinhood_ed25519_private.b64").write_text("secret-private")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    source_report = intel.build_source_report()

    assert source_report["robinhood"]["configured"] is True
    assert "secret-key" not in str(source_report)
    assert "secret-private" not in str(source_report)


def test_probe_source_mesh_non_live_does_not_touch_network(tmp_path):
    pack_path = tmp_path / "research.zip"
    _write_research_zip(pack_path)

    probes = intel.probe_source_mesh(pack_path, live=False)
    statuses = {row["id"]: row for row in probes["probes"]}

    assert probes["mode"] == "read-only"
    assert probes["live_requested"] is False
    assert statuses["kimi_research_pack"]["status"] == "ready"
    assert statuses["sec_company_tickers"]["status"] == "not_requested"
    assert probes["series_catalog"]


def test_probe_source_mesh_live_uses_read_only_callbacks(monkeypatch, tmp_path):
    pack_path = tmp_path / "research.zip"
    _write_research_zip(pack_path)
    monkeypatch.setenv(intel.SEC_USER_AGENT_ENV, "sapphire-test contact@example.com")
    monkeypatch.setattr(intel, "_request_json", lambda *_args, **_kwargs: {"0": {"ticker": "AAPL"}})
    monkeypatch.setattr(
        intel,
        "build_crypto_bridge",
        lambda *_args, **_kwargs: {"trending": [{"symbol": "HYPE"}]},
    )
    monkeypatch.setattr(intel, "_probe_hyperliquid", lambda: ("ok", 3))
    monkeypatch.setattr(intel, "_probe_defillama", lambda: ("ok", 4))

    probes = intel.probe_source_mesh(pack_path, live=True)
    statuses = {row["id"]: row for row in probes["probes"]}

    assert statuses["sec_company_tickers"]["status"] == "ready"
    assert statuses["coingecko_market"]["observed_count"] == 1
    assert statuses["hyperliquid_info"]["observed_count"] == 3
    assert statuses["defillama_defi"]["observed_count"] == 4


def test_materialization_preview_builds_rows_and_writes_ndjson(tmp_path):
    pack_path = tmp_path / "research.zip"
    _write_research_zip(pack_path)
    report = intel.build_investment_intel_report(pack_path)

    rows = intel.build_materialization_rows(report)
    assert rows["investment_assets"]
    assert rows["investment_source_coverage"]
    assert rows["investment_research_pack"][0]["csv_asset_count"] == 1

    out = intel.write_materialization_preview(tmp_path / "stage", zip_path=pack_path)

    assert out["mode"] == "dry-run-write"
    assert out["total_rows"] == sum(item["rows"] for item in out["written"])
    first = Path(out["written"][0]["path"])
    assert first.exists()
    assert json.loads(first.read_text(encoding="utf-8").splitlines()[0])["timestamp"]


def test_public_source_clients_construct_official_urls(monkeypatch):
    calls = []

    def fake_request(url, *, headers=None, params=None, timeout=intel.DEFAULT_TIMEOUT):
        calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        return {"ok": True}

    monkeypatch.setattr(intel, "_request_json", fake_request)

    assert intel.SecEdgarClient(user_agent="ua").submissions("320193") == {"ok": True}
    assert intel.SecEdgarClient(user_agent="ua").companyfacts("320193") == {"ok": True}
    assert intel.FredClient(api_key="fred-key").series_observations("DGS10") == {"ok": True}
    assert intel.EiaClient(api_key="eia-key").route_data("electricity/retail-sales") == {"ok": True}

    assert calls[0]["url"].endswith("/submissions/CIK0000320193.json")
    assert calls[1]["url"].endswith("/api/xbrl/companyfacts/CIK0000320193.json")
    assert calls[2]["params"]["series_id"] == "DGS10"
    assert calls[2]["params"]["api_key"] == "fred-key"
    assert calls[3]["url"].endswith("/v2/electricity/retail-sales/data")
    assert calls[3]["params"]["api_key"] == "eia-key"


def test_fred_and_eia_require_keys(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("EIA_API_KEY", raising=False)

    with pytest.raises(intel.SourceHTTPError):
        intel.FredClient().series_observations("DGS10")
    with pytest.raises(intel.SourceHTTPError):
        intel.EiaClient().route_data("electricity/retail-sales")
