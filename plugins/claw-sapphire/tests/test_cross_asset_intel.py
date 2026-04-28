"""Tests for the Sapphire cross_asset_intel plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "cross_asset_intel.py"

_spec = importlib.util.spec_from_file_location("cross_asset_intel_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
cai = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cai
_spec.loader.exec_module(cai)


def _sample_snapshot(**overrides):
    payload = {
        "ok": True,
        "mode": "cache_or_dry_run",
        "generated_at": "2026-04-28T12:00:00+00:00",
        "matrix": {
            "windows": {
                "7d": {
                    "pearson": {
                        "method": "pearson",
                        "window": "7d",
                        "assets": ["BTC", "ETH"],
                        "matrix": [[1.0, 0.8], [0.8, 1.0]],
                    }
                }
            }
        },
        "regime": {"label": "risk_on_correlated", "confidence": 0.8},
        "breakdowns": [{"pair": ["BTC", "ETH"], "z_score": -2.1}],
        "lead_lag": [{"pair": ["BTC", "ETH"], "best_lag": 1, "correlation": 0.7}],
        "provenance": {"schema_version": 1},
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def fake_snapshot(monkeypatch):
    calls = []

    def build_snapshot(**kwargs):
        calls.append(kwargs)
        return _sample_snapshot()

    monkeypatch.setattr(cai, "build_snapshot", build_snapshot)
    return calls


def test_status_action_does_not_fetch_snapshot(fake_snapshot) -> None:
    status = cai.status_action()
    assert status["ok"] is True
    assert status["caps"]["max_assets_hard"] == 24
    assert fake_snapshot == []


def test_matrix_action_returns_selected_matrix(fake_snapshot) -> None:
    out = cai.handle({"action": "matrix", "window": "7d", "method": "pearson"})
    assert out["ok"] is True
    assert out["matrix"]["assets"] == ["BTC", "ETH"]
    assert out["breakdown_count"] == 1


def test_matrix_action_falls_back_to_available_matrix() -> None:
    out = cai.handle({"action": "matrix", "window": "30d", "method": "kendall"})
    assert out["ok"] is True
    assert out["window"] == "7d"
    assert out["method"] == "pearson"


def test_regime_action_returns_label() -> None:
    out = cai.handle({"action": "regime"})
    assert out["regime"]["label"] == "risk_on_correlated"


def test_breakdowns_action_honors_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        cai,
        "build_snapshot",
        lambda **kwargs: _sample_snapshot(breakdowns=[{"idx": 1}, {"idx": 2}]),
    )
    out = cai.handle({"action": "breakdowns", "limit": 1})
    assert out["breakdowns"] == [{"idx": 1}]


def test_lead_lag_action_honors_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        cai,
        "build_snapshot",
        lambda **kwargs: _sample_snapshot(lead_lag=[{"idx": 1}, {"idx": 2}]),
    )
    out = cai.handle({"action": "lead-lag", "limit": 1})
    assert out["lead_lag"] == [{"idx": 1}]


def test_assets_are_coerced_and_live_flag_is_forwarded(fake_snapshot) -> None:
    out = cai.handle({"action": "matrix", "assets": "btc, eth,btc", "live": True})
    assert out["ok"] is True
    assert fake_snapshot[-1]["assets"] == ["BTC", "ETH"]
    assert fake_snapshot[-1]["live"] is True


def test_too_many_assets_returns_error() -> None:
    out = cai.handle({"action": "matrix", "assets": [f"A{i}" for i in range(25)]})
    assert "MAX_ASSETS_HARD" in out["error"]


def test_unknown_action_returns_valid_actions() -> None:
    out = cai.handle({"action": "wat"})
    assert "error" in out
    assert "matrix" in out["valid_actions"]


def test_main_reads_stdin_and_writes_json() -> None:
    out_buf = io.StringIO()
    rc = cai.main(stream_in=io.StringIO(json.dumps({"action": "regime"})), stream_out=out_buf)
    assert rc == 0
    parsed = json.loads(out_buf.getvalue())
    assert parsed["regime"]["label"] == "risk_on_correlated"


def test_main_rejects_invalid_json() -> None:
    out_buf = io.StringIO()
    rc = cai.main(stream_in=io.StringIO("{no"), stream_out=out_buf)
    assert rc == 2
    assert "invalid JSON" in out_buf.getvalue()


def test_main_rejects_non_object_payload() -> None:
    out_buf = io.StringIO()
    rc = cai.main(stream_in=io.StringIO("[1,2]"), stream_out=out_buf)
    assert rc == 2
