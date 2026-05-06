"""Tests for the x402 market-regime paid artifact builder."""

from __future__ import annotations

from lib.payments.x402_market_regime import artifact_id_for_report, build_market_regime_report
from lib.payments.x402_products import load_product_catalog, load_source_registry


def _snapshot() -> dict:
    return {
        "ok": True,
        "mode": "cache_or_dry_run",
        "generated_at": "2026-05-06T15:30:00Z",
        "assets": ["BTC", "ETH", "SPY"],
        "regime": {
            "timestamp": "2026-05-06T15:30:00Z",
            "label": "risk_on_correlated",
            "confidence": 0.82,
            "drivers": ["risk assets positively correlated"],
            "metrics": {"observed_pairs": 3, "risk_asset_correlation": 0.71},
        },
        "breakdowns": [{"pair": ["BTC", "ETH"], "severity": "low"}],
        "lead_lag": [{"pair": ["BTC", "ETH"], "best_lag": 1}],
        "source_summary": {"BTC": {"points": 100, "source": "fixture"}},
        "provenance": {"generator": "test"},
    }


def test_market_regime_report_is_catalog_grounded() -> None:
    product = load_product_catalog().get("market_regime_report")
    registry = load_source_registry()

    report = build_market_regime_report(
        product=product,
        registry=registry,
        snapshot=_snapshot(),
        generated_at="2026-05-06T15:30:00Z",
    )

    assert report["product_id"] == "market_regime_report"
    assert report["artifact_kind"] == "market_regime_report"
    assert report["settlement_mode"] == "simulated_or_testnet"
    assert report["live_settlement_allowed"] is False
    assert report["summary"]["label"] == "risk_on_correlated"
    assert report["summary"]["asset_count"] == 3
    assert report["summary"]["breakdown_count"] == 1
    assert report["artifact_id"].startswith("x402-mr-")
    assert {source["source_id"] for source in report["catalog_sources"]} >= {
        "defillama",
        "fred_alfred",
        "gdelt_2",
        "sec_edgar",
    }


def test_market_regime_artifact_id_is_deterministic() -> None:
    product = load_product_catalog().get("market_regime_report")
    registry = load_source_registry()
    report = build_market_regime_report(
        product=product,
        registry=registry,
        snapshot=_snapshot(),
        generated_at="2026-05-06T15:30:00Z",
    )

    artifact_id = report.pop("artifact_id")

    assert artifact_id == artifact_id_for_report(report)


def test_market_regime_report_surfaces_snapshot_degradation() -> None:
    product = load_product_catalog().get("market_regime_report")
    registry = load_source_registry()
    snapshot = {**_snapshot(), "ok": False}

    report = build_market_regime_report(
        product=product,
        registry=registry,
        snapshot=snapshot,
        generated_at="2026-05-06T15:30:00Z",
    )

    assert report["ok"] is False
    assert "source snapshot reported unavailable or degraded" in report["warnings"]
