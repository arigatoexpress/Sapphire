from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_gcp_sync(monkeypatch: pytest.MonkeyPatch):
    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_storage = types.ModuleType("google.cloud.storage")
    fake_cloud.bigquery = fake_bigquery
    fake_cloud.storage = fake_storage

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", fake_storage)

    module_name = "gcp_sync_signals_test"
    module_path = ROOT / "services" / "pipeline" / "gcp_sync.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_signal_source_discovers_scored_and_legacy_signal_logs(monkeypatch, tmp_path):
    gcp_sync = _load_gcp_sync(monkeypatch)
    data_dir = tmp_path / "data"
    signals_dir = data_dir / "signals"
    signals_dir.mkdir(parents=True)
    scored = signals_dir / "2026-05-10.jsonl"
    legacy = data_dir / "trading_signals.jsonl"
    unrelated = data_dir / "paper_trading.jsonl"
    scored.write_text("{}", encoding="utf-8")
    legacy.write_text("{}", encoding="utf-8")
    unrelated.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gcp_sync, "DATA_DIR", data_dir)

    discovered = gcp_sync._discover_files(gcp_sync.SOURCES["signals"].glob, since_mtime=0)

    assert discovered == [scored, legacy]


def test_transform_signals_maps_legacy_signal_logger_rows(monkeypatch, tmp_path):
    gcp_sync = _load_gcp_sync(monkeypatch)
    legacy = tmp_path / "trading_signals.jsonl"
    legacy.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-10T12:00:00+00:00",
                "symbol": "BTC-USD",
                "action": "BUY",
                "strategy": "test-paper",
                "price": 84500,
                "confidence": 0.75,
                "signal_id": "legacy-1",
                "source": "webhook",
                "raw": {"note": "not emitted separately"},
            }
        )
        + "\nnot-json\n",
        encoding="utf-8",
    )

    rows = list(gcp_sync.transform_signals([legacy]))

    assert len(rows) == 1
    row = rows[0]
    assert row["signal_id"] == "legacy-1"
    assert row["symbol"] == "BTC-USD"
    assert row["action"] == "buy"
    assert row["source"] == "webhook"
    assert row["price_at_signal"] == 84500
    assert row["confidence"] == 0.75
    assert row["timestamp"] == "2026-05-10T12:00:00+00:00"
