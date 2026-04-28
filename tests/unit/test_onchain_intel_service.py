"""Tests for services.onchain_intel."""

from __future__ import annotations

import json

from services.onchain_intel import run, run_once, service


def test_build_status_does_not_require_live_env(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_GLASSNODE_LIVE", raising=False)

    status = service.build_status()

    assert status["service"] == "onchain_intel"
    assert status["mode"] == "fixture"
    assert status["wallet_keys_required"] is False
    assert status["trading_enabled"] is False


def test_write_snapshot_writes_latest_and_archive(tmp_path):
    snapshot = {"schema_version": "0.2.0", "generated_at": "2026-04-28T12:00:00+00:00"}

    paths = service.write_snapshot(snapshot, latest_dir=tmp_path / "latest")

    latest = tmp_path / "latest" / "onchain_intel.json"
    assert paths["latest_path"] == str(latest)
    assert latest.exists()
    assert (tmp_path / "latest" / "onchain_intel.json.envelope.json").exists()
    assert json.loads(latest.read_text())["schema_version"] == "0.2.0"
    assert (tmp_path / "latest" / "archive").exists()


def test_run_once_can_skip_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))

    snapshot = run_once.run_once(assets=["BTC"], backfill_days=30, write=False)

    assert "paths" not in snapshot
    assert snapshot["assets"]["BTC"]["glassnode"]["mode"] == "fixture"


def test_run_module_status_and_no_write_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))

    status = run.build_status()
    snapshot = run.run_once(assets=["ETH"], backfill_days=5, write=False, publish=True)

    assert status["service"] == "onchain_intel"
    assert snapshot["assets"]["ETH"]["santiment"]["network_growth"] == 74000
    assert snapshot["published"] == {"requested": True, "actual": False, "published": 0}
    assert snapshot["service"]["event_topic"] == "onchain.snapshot.updated"
