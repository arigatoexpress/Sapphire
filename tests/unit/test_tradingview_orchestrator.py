"""Unit tests for TradingView orchestrator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lib.trading.tradingview_orchestrator import (
    TradingViewOrchestrator,
    TVCommandError,
)


@pytest.fixture
def tmp_artifact_root(tmp_path: Path) -> Path:
    return tmp_path / "tv_ta"


@pytest.fixture
def orch(tmp_artifact_root: Path) -> TradingViewOrchestrator:
    return TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )


def test_orchestrator_mutation_gate_defaults_off():
    with patch.dict(os.environ, {}, clear=True):
        o = TradingViewOrchestrator(tv_bin="echo")
        assert o.mutation_enabled is False


def test_orchestrator_mutation_gate_respects_env():
    with patch.dict(os.environ, {"SAPPHIRE_TV_MUTATION_ENABLED": "1"}):
        o = TradingViewOrchestrator(tv_bin="echo")
        assert o.mutation_enabled is True


def test_probe_state_returns_dict(orch: TradingViewOrchestrator):
    with patch.object(orch, "_run", return_value={"ok": True, "payload": {"symbol": "A"}}):
        res = orch.probe_state()
        assert res["ok"] is True


def test_set_symbol_blocked_without_gate(orch: TradingViewOrchestrator):
    res = orch.set_symbol("BINANCE:BTCUSDT")
    assert res["mutated"] is False
    assert "SAPPHIRE_TV_MUTATION_ENABLED" in res["reason"]


def test_setup_chart_blocked_without_gate(orch: TradingViewOrchestrator):
    res = orch.setup_chart("BINANCE:BTCUSDT", "60")
    assert res["mutated"] is False


def test_apply_indicator_stack_blocked_without_gate(orch: TradingViewOrchestrator):
    res = orch.apply_indicator_stack()
    assert res["mutated"] is False


def test_run_json_parse_success(orch: TradingViewOrchestrator):
    fake_payload = {"success": True, "symbol": "BINANCE:ETHUSDT"}
    with patch.object(
        orch,
        "_run",
        return_value={
            "ok": True,
            "payload": fake_payload,
            "command": "tv state",
            "returncode": 0,
            "stderr": "",
        },
    ):
        res = orch.probe_state()
        assert res["payload"]["symbol"] == "BINANCE:ETHUSDT"


def test_run_json_parse_failure(orch: TradingViewOrchestrator):
    with patch.object(
        orch,
        "_run",
        return_value={
            "ok": True,
            "stdout": "not-json",
            "payload": None,
            "parse_error": "bad json",
            "command": "tv state",
            "returncode": 0,
            "stderr": "",
        },
    ):
        res = orch.probe_state()
        assert res["parse_error"] == "bad json"


def test_require_ok_raises_on_failure(orch: TradingViewOrchestrator):
    bad = {
        "ok": False,
        "command": "tv bad",
        "returncode": 1,
        "stderr": "error",
    }
    with pytest.raises(TVCommandError):
        orch._require_ok(bad)


def test_safe_filename(orch: TradingViewOrchestrator):
    assert orch._safe_filename("BINANCE:ETHUSDT", "60", "ss.png") == "BINANCE_ETHUSDT_60_ss.png"
    assert orch._safe_filename("BTC/USD", "D", "ohlcv.json") == "BTC_USD_D_ohlcv.json"


def test_capture_sweep_read_only_no_mutations(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )
    symbols = [
        {"symbol": "ETH", "tradingview_symbol": "BINANCE:ETHUSDT", "rank": 1},
    ]
    with patch.object(orch, "screenshot", return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"}):
        with patch.object(orch, "probe_ohlcv", return_value={"ok": True}):
            with patch.object(orch, "probe_quote", return_value={"ok": True}):
                manifest = orch.capture_sweep(symbols, session_id="test-session")

    assert manifest["schema_version"] == "tradingview-orchestrator.sweep_capture.v1"
    assert manifest["mutation_enabled"] is False
    assert manifest["session_id"] == "test-session"
    assert len(manifest["symbols"]) == 1
    assert manifest["symbols"][0]["symbol"] == "ETH"
    manifest_path = tmp_artifact_root / "test-session" / "manifest.json"
    assert manifest_path.exists()


def test_capture_deep_read_only_no_mutations(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )
    with patch.object(orch, "screenshot", return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"}):
        with patch.object(orch, "probe_ohlcv", return_value={"ok": True}):
            with patch.object(orch, "probe_values", return_value={"ok": True}):
                with patch.object(orch, "probe_quote", return_value={"ok": True}):
                    manifest = orch.capture_symbol_deep(
                        "ETH", "BINANCE:ETHUSDT", timeframes=["60"], session_id="deep-test"
                    )

    assert manifest["schema_version"] == "tradingview-orchestrator.deep_capture.v1"
    assert manifest["symbol"] == "ETH"
    assert len(manifest["timeframes"]) == 1
    manifest_path = tmp_artifact_root / "deep-test" / "manifest.json"
    assert manifest_path.exists()


def test_latest_manifest_returns_none_when_empty(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(tv_bin="echo", artifact_root=tmp_artifact_root)
    assert orch.latest_manifest() is None


def test_list_sessions_empty(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(tv_bin="echo", artifact_root=tmp_artifact_root)
    assert orch.list_sessions() == []


def test_list_sessions_with_manifests(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(tv_bin="echo", artifact_root=tmp_artifact_root)
    session = tmp_artifact_root / "20260101T000000Z"
    session.mkdir(parents=True)
    (session / "manifest.json").write_text(
        json.dumps({
            "generated_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "v1",
            "symbols": [{}, {}],
            "timeframes": [],
        }),
        encoding="utf-8",
    )
    results = orch.list_sessions()
    assert len(results) == 1
    assert results[0]["session_id"] == "20260101T000000Z"
    assert results[0]["symbol_count"] == 2
