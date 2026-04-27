"""Tests for the read-only sovereign thesis matrix."""

from __future__ import annotations

import json
from pathlib import Path

from lib.intel.sovereign_thesis import (
    build_sovereign_thesis_report,
    build_thesis_materialization_rows,
    load_thesis_config,
    parse_assets,
    parse_lenses,
    write_thesis_materialization_preview,
)


def _config() -> dict:
    return {
        "worldview": {"stance": "unit", "principles": ["falsifiable_theses"]},
        "lenses": [
            {
                "id": "hard_money",
                "label": "Hard Money",
                "weight": 2.0,
                "austrian_principle": "fixed supply",
                "positive_tags": ["hard_money"],
                "negative_tags": ["fiat_beta"],
                "source_requirements": ["coingecko:market_data", "fred:M2SL"],
            },
            {
                "id": "energy",
                "label": "Energy",
                "weight": 1.0,
                "austrian_principle": "cheap energy",
                "positive_tags": ["energy"],
                "negative_tags": [],
                "source_requirements": ["eia:electricity"],
            },
        ],
        "assets": [
            {
                "symbol": "BTC",
                "name": "Bitcoin",
                "asset_class": "crypto",
                "conviction": 0.9,
                "thesis_tags": ["hard_money"],
                "lens_scores": {"hard_money": 1.0},
                "venue_symbols": {"tradingview": "BINANCE:BTCUSDT"},
                "evidence_sources": ["coingecko:market_data"],
                "invalidation_triggers": [
                    {"id": "custody_capture", "condition": "custodial claims dominate", "severity": "high"}
                ],
            },
            {
                "symbol": "GRID",
                "name": "GridCo",
                "asset_class": "equity",
                "conviction": 0.5,
                "thesis_tags": ["energy"],
                "evidence_sources": [],
            },
        ],
        "source_docs": [{"id": "coingecko:market_data", "url": "https://example.test"}],
    }


def test_load_thesis_config_accepts_json_compatible_yaml(tmp_path) -> None:
    path = tmp_path / "thesis.yaml"
    path.write_text(json.dumps(_config()), encoding="utf-8")

    loaded = load_thesis_config(path)

    assert loaded["worldview"]["stance"] == "unit"
    assert parse_lenses(loaded)[0].id == "hard_money"
    assert parse_assets(loaded)[0].symbol == "BTC"


def test_build_sovereign_thesis_report_ranks_assets_and_gaps(tmp_path) -> None:
    path = tmp_path / "thesis.yaml"
    path.write_text(json.dumps(_config()), encoding="utf-8")

    report = build_sovereign_thesis_report(path)

    assert report["mode"] == "research_intel_only"
    assert report["safety"]["live_trading_enabled"] is False
    assert report["safety"]["execution_enabled"] is False
    assert report["totals"]["assets"] == 2
    assert report["totals"]["lenses"] == 2
    assert report["totals"]["evidence_required"] == 3
    assert report["totals"]["evidence_coverage_pct"] == 33.3
    assert report["totals"]["evidence_wired_pct"] == 100.0
    assert report["assets"][0]["symbol"] == "BTC"
    assert report["assets"][0]["fit"] == "core"
    assert report["assets"][0]["source_gaps"] == ["fred:M2SL"]
    assert report["assets"][0]["evidence_summary"] == {
        "coverage_pct": 50.0,
        "evidenced": 1,
        "needs_wiring": 0,
        "provider_wired": 1,
        "required": 2,
        "wired_pct": 100.0,
    }
    assert {row["source_id"]: row["status"] for row in report["assets"][0]["evidence_ledger"]} == {
        "coingecko:market_data": "evidenced",
        "fred:M2SL": "provider_wired",
    }
    assert report["assets"][1]["symbol"] == "GRID"
    assert "eia:electricity" in report["assets"][1]["source_gaps"]
    assert report["evidence_summary"]["required"] == 3
    assert report["materialization_plan"]["writes_by_default"] is False
    assert report["materialization_plan"]["total_rows"] > len(report["assets"])
    assert report["ops_queue"][0]["safe_mode"] == "read_only"
    assert report["invalidation_queue"][0]["symbol"] == "BTC"
    assert {row["id"] for row in report["source_requirements"]} >= {"coingecko:market_data", "fred:M2SL"}


def test_default_sovereign_thesis_report_covers_ari_universe() -> None:
    report = build_sovereign_thesis_report()
    rows = {row["symbol"]: row for row in report["assets"]}

    assert report["worldview"]["stance"] == "cypherpunk_austrian"
    assert report["safety"]["telegram_sends_enabled"] is False
    assert report["totals"]["assets"] >= 20
    assert rows["BTC"]["fit"] == "core"
    assert "hard_money" in rows["BTC"]["aligned_lenses"]
    assert "self_custody" in rows["BTC"]["aligned_lenses"]
    assert "censorship_resistance" in rows["ZEC"]["aligned_lenses"]
    assert rows["XMR"]["asset_class"] == "crypto_watch"
    assert rows["BWXT"]["asset_class"] == "equity"
    assert rows["SHLD"]["name"] == "Global X Defense Tech ETF"
    assert rows["PLTR"]["venue_symbols"]["tradingview"] == "NASDAQ:PLTR"
    assert report["evidence_summary"]["required"] >= 250
    assert 0 < report["totals"]["evidence_coverage_pct"] < report["totals"]["evidence_wired_pct"]
    assert rows["BTC"]["evidence_summary"]["needs_wiring"] >= 1
    assert "fred:M2SL" in {row["source_id"] for row in rows["BTC"]["evidence_ledger"]}


def test_default_sovereign_thesis_tracks_invalidations_and_sources() -> None:
    report = build_sovereign_thesis_report()
    requirements = {row["id"]: row for row in report["source_requirements"]}

    assert report["invalidation_queue"]
    assert report["totals"]["tripped_invalidations"] == 0
    assert any(flag["symbol"] == "BTC" for flag in report["invalidation_queue"])
    assert report["ops_queue"]
    assert all(
        item["safe_mode"] in {"read_only", "research_only", "metadata_only"}
        for item in report["ops_queue"]
    )
    assert "sec:companyfacts" in requirements
    assert "coingecko:market_data" in requirements
    assert "hyperliquid:asset_contexts" in requirements
    assert requirements["policy:jurisdiction_scan"]["configured"] is False
    assert requirements["policy:jurisdiction_scan"]["needs_wiring"] >= 1
    assert any(row["status"] == "needs_wiring" for row in report["evidence_ledger"])


def test_sovereign_thesis_materialization_preview_is_explicit_dry_run(tmp_path) -> None:
    path = tmp_path / "thesis.yaml"
    path.write_text(json.dumps(_config()), encoding="utf-8")
    report = build_sovereign_thesis_report(path)

    rows = build_thesis_materialization_rows(report)

    assert rows["sovereign_thesis_assets"][0]["symbol"] == "BTC"
    assert rows["sovereign_thesis_evidence_ledger"]
    assert rows["sovereign_thesis_ops_queue"]

    preview = write_thesis_materialization_preview(tmp_path / "stage", config_path=path)

    assert preview["mode"] == "dry-run-write"
    assert preview["total_rows"] == sum(row["rows"] for row in preview["written"])
    assert {row["table"] for row in preview["written"]} == set(rows)
    for row in preview["written"]:
        target = Path(row["path"])
        assert target.exists()
        if row["rows"]:
            assert target.read_text(encoding="utf-8").strip()
