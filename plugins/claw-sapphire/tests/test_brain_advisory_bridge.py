"""Tests for the quant-perps brain → Sapphire advisory bridge.

The bridge reads ``~/ops-state/advisory/advisory-latest.json`` and exposes it in a
Sapphire-native shape. These tests redirect the advisory path to a temp file and
verify read/decide/dashboard/publish behavior, including stale handling and the
advisory-only banner.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "brain_advisory_bridge.py"
_spec = importlib.util.spec_from_file_location("brain_advisory_bridge", INTERNAL)
assert _spec is not None and _spec.loader is not None
bridge = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = bridge
_spec.loader.exec_module(bridge)


@pytest.fixture
def fresh_advisory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a current advisory file and point the bridge at it."""
    advisory = tmp_path / "advisory-latest.json"
    advisory.write_text(json.dumps(_sample_advisory()), encoding="utf-8")
    monkeypatch.setattr(bridge, "ADVISORY_PATH", advisory)
    monkeypatch.setattr(bridge, "ADVISORY_STALE_SECONDS", 3600)
    return advisory


def _sample_advisory(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "date": "2026-07-11",
        "generated_ts": int(time.time()),
        "forecaster": "remote forecaster: enabled",
        "sample": False,
        "banner": "**ADVISORY ONLY — no orders are placed by this system.**",
        "rows": [
            {
                "symbol": "MSTR",
                "signal": "FLAT",
                "regime": "trending",
                "score": None,
                "close": 94.64,
                "is_reference": False,
                "forecast": {"point": 99.10, "lo": 77.18, "hi": 119.74, "horizon": 5},
            },
            {
                "symbol": "IBIT",
                "signal": "LONG",
                "regime": "trending",
                "score": 0.72,
                "close": 36.23,
                "is_reference": False,
                "forecast": {"point": 37.47, "lo": 33.96, "hi": 40.87, "horizon": 5},
            },
            {
                "symbol": "TSLA",
                "signal": "FLAT",
                "regime": "ranging",
                "score": None,
                "close": 407.76,
                "is_reference": False,
                "forecast": {"point": 408.28, "lo": 381.24, "hi": 441.27, "horizon": 5},
            },
            {
                "symbol": "SPY",
                "signal": "REFERENCE",
                "regime": "transition",
                "score": None,
                "close": 754.95,
                "is_reference": True,
                "forecast": None,
            },
        ],
    }
    base.update(overrides)
    return base


def test_action_read_returns_rows_and_metadata(fresh_advisory: Path) -> None:
    result = bridge.action_read()
    assert result["success"] is True
    assert result["exists"] is True
    assert result["stale"] is False
    assert result["row_count"] == 4
    assert result["advisory_path"] == str(fresh_advisory)
    assert result["banner"] == "**ADVISORY ONLY — no orders are placed by this system.**"


def test_action_read_reports_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(bridge, "ADVISORY_PATH", missing)
    result = bridge.action_read()
    assert result["success"] is False
    assert result["exists"] is False
    assert "not found" in result["error"]


def test_action_decide_maps_btc_to_ibit_long(fresh_advisory: Path) -> None:
    result = bridge.action_decide("BTC")
    assert result["symbol"] == "BTC"
    assert result["proxy_symbol"] == "IBIT"
    assert result["signal"] == "GO_LONG"
    assert result["direction"] == "bullish"
    assert result["source"] == "BrainAdvisory"
    assert result["advisory_stale"] is False
    assert "IBIT" in result["detail"]


def test_action_decide_direct_advisory_symbol(fresh_advisory: Path) -> None:
    result = bridge.action_decide("TSLA")
    assert result["symbol"] == "TSLA"
    assert "proxy_symbol" not in result
    assert result["signal"] == "WAIT"
    assert result["direction"] == "neutral"


def test_action_decide_unknown_symbol(fresh_advisory: Path) -> None:
    result = bridge.action_decide("XYZ")
    assert result["symbol"] == "XYZ"
    assert result["signal"] == "WAIT"
    assert result["direction"] == "neutral"


def test_action_dashboard_includes_proxies_and_direct_symbols(fresh_advisory: Path) -> None:
    result = bridge.action_dashboard()
    assert result["success"] is True
    decisions = result["decisions"]
    # Native proxies.
    assert "BTC" in decisions
    assert decisions["BTC"]["proxy_symbol"] == "IBIT"
    # Direct advisory symbols (SPY is reference and should still appear).
    assert "MSTR" in decisions
    assert "TSLA" in decisions
    assert "SPY" in decisions


def test_action_publish_is_dry_run_by_default(fresh_advisory: Path) -> None:
    result = bridge.action_publish(live=False)
    assert result["mode"] == "dry-run"
    assert result["success"] is True
    assert result["count"] == 1
    sig = result["signals"][0]
    assert sig["symbol"] == "IBIT"
    assert sig["direction"] == "long"
    assert sig["live"] is False
    assert "no transaction signed" in result["note"]


def test_action_publish_ignores_flat_and_reference_rows(fresh_advisory: Path) -> None:
    result = bridge.action_publish(live=False)
    symbols = {s["symbol"] for s in result["signals"]}
    assert "MSTR" not in symbols
    assert "TSLA" not in symbols
    assert "SPY" not in symbols


def test_stale_advisory_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = _sample_advisory(generated_ts=int(time.time()) - 90000)
    advisory = tmp_path / "stale.json"
    advisory.write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(bridge, "ADVISORY_PATH", advisory)
    monkeypatch.setattr(bridge, "ADVISORY_STALE_SECONDS", 3600)

    result = bridge.action_read()
    assert result["stale"] is True

    decide = bridge.action_decide("BTC")
    assert decide["advisory_stale"] is True
