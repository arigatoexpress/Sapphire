"""Hermetic tests for on-chain intelligence 0.2.0 aggregator."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from lib.chain import aggregator


def test_provider_matrix_defaults_to_fixture(monkeypatch):
    for name in (
        "SAPPHIRE_GLASSNODE_LIVE",
        "SAPPHIRE_SANTIMENT_LIVE",
        "SAPPHIRE_ETH_NODE_LIVE",
        "SAPPHIRE_SOL_NODE_LIVE",
        "GLASSNODE_API_KEY",
        "SANTIMENT_API_KEY",
        "ETH_RPC_URL",
        "SOL_RPC_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    matrix = aggregator.provider_matrix()

    assert matrix["glassnode"]["live_enabled"] is False
    assert matrix["eth_node"]["mode"] == "fixture"


def test_clamp_backfill_days_caps_at_730():
    assert aggregator.clamp_backfill_days(9999) == 730
    assert aggregator.clamp_backfill_days(0) == 1
    assert aggregator.clamp_backfill_days("bad") == 30


def test_enforce_provider_cap_raises_before_hourly_overage(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    aggregator.enforce_provider_cap("glassnode", cost=2, now=now, hour_cap=2)

    with pytest.raises(aggregator.RateCapError):
        aggregator.enforce_provider_cap("glassnode", cost=1, now=now, hour_cap=2)


def test_build_snapshot_fixture_mode_zero_live(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    for name in (
        "SAPPHIRE_GLASSNODE_LIVE",
        "SAPPHIRE_SANTIMENT_LIVE",
        "SAPPHIRE_ETH_NODE_LIVE",
        "SAPPHIRE_SOL_NODE_LIVE",
    ):
        monkeypatch.delenv(name, raising=False)

    snap = aggregator.build_snapshot(assets=["BTC"], backfill_days=9999)

    assert snap["schema_version"] == "0.2.0"
    assert snap["summary"]["mode"] == "fixture"
    assert snap["summary"]["live_provider_count"] == 0
    assert snap["limits"]["backfill_days_requested"] == 730
    assert snap["wallet_keys_required"] is False
    assert snap["trading_enabled"] is False
    assert snap["assets"]["BTC"]["glassnode"]["mode"] == "fixture"
    assert snap["assets"]["BTC"]["composite"]["onchain_heat_score"] > 0
    assert snap["nodes"]["ethereum"]["read_only"] is True
    assert not (tmp_path / "usage.json").exists()


def test_usage_ledger_records_counts(tmp_path, monkeypatch):
    usage = tmp_path / "usage.json"
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(usage))

    out = aggregator.enforce_provider_cap(
        "santiment",
        now=datetime(2026, 4, 28, 12, 30, tzinfo=UTC),
    )

    assert out == {"hour": 1, "day": 1}
    data = json.loads(usage.read_text())
    assert data["santiment"]["daily"]["2026-04-28"] == 1
