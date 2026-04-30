"""Unit tests for TradingView orchestrator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lib.trading.tradingview_orchestrator import (
    EVENT_PINE_BATCH_COMPLETED,
    EVENT_SESSION_COMPLETED,
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
    with patch("lib.trading.tradingview_orchestrator._emit_event"), patch.object(orch, "screenshot", return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"}):
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
    with patch("lib.trading.tradingview_orchestrator._emit_event"), patch.object(orch, "screenshot", return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"}):
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


def test_capture_sweep_emits_session_completed_event(tmp_artifact_root: Path):
    """capture_sweep must publish exactly one session_completed event."""
    orch = TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )
    symbols = [
        {"symbol": "ETH", "tradingview_symbol": "BINANCE:ETHUSDT", "rank": 1},
        {"symbol": "BTC", "tradingview_symbol": "BINANCE:BTCUSDT", "rank": 2},
    ]
    published: list[tuple[str, dict]] = []

    def fake_publish(event_type: str, data: dict, source: str | None = None) -> str:
        published.append((event_type, data))
        return "fake-id"

    fake_bus_module = type("M", (), {"publish": staticmethod(fake_publish)})
    with patch.dict(
        "sys.modules", {"lib.core.event_bus": fake_bus_module}
    ), patch.object(
        orch, "screenshot",
        return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"},
    ), patch.object(
        orch, "probe_ohlcv", return_value={"ok": True}
    ), patch.object(
        orch, "probe_quote", return_value={"ok": True}
    ):
        manifest = orch.capture_sweep(symbols, session_id="evt-test-sweep")

    assert len(published) == 1, f"expected exactly one event, got {published}"
    event_type, payload = published[0]
    assert event_type == EVENT_SESSION_COMPLETED
    assert payload["session_id"] == "evt-test-sweep"
    assert payload["schema_version"] == manifest["schema_version"]
    assert payload["symbol_count"] == 2
    assert payload["timeframe_count"] == 1
    assert payload["manifest_path"].endswith("manifest.json")
    # Payload must be JSON-serializable for the bus.
    json.dumps(payload)


def test_capture_symbol_deep_emits_session_completed_event(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )
    published: list[tuple[str, dict]] = []

    def fake_publish(event_type: str, data: dict, source: str | None = None) -> str:
        published.append((event_type, data))
        return "fake-id"

    fake_bus_module = type("M", (), {"publish": staticmethod(fake_publish)})
    with patch.dict(
        "sys.modules", {"lib.core.event_bus": fake_bus_module}
    ), patch.object(
        orch, "screenshot",
        return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"},
    ), patch.object(
        orch, "probe_ohlcv", return_value={"ok": True}
    ), patch.object(
        orch, "probe_values", return_value={"ok": True}
    ), patch.object(
        orch, "probe_quote", return_value={"ok": True}
    ):
        manifest = orch.capture_symbol_deep(
            "ETH", "BINANCE:ETHUSDT", timeframes=["60", "240"], session_id="evt-test-deep"
        )

    assert len(published) == 1
    event_type, payload = published[0]
    assert event_type == EVENT_SESSION_COMPLETED
    assert payload["session_id"] == "evt-test-deep"
    assert payload["schema_version"] == manifest["schema_version"]
    assert payload["symbol_count"] == 1
    assert payload["timeframe_count"] == 2
    assert payload["manifest_path"].endswith("manifest.json")


def test_emit_event_swallows_bus_failures(tmp_artifact_root: Path):
    """If the event bus raises, capture must still complete normally."""
    from lib.trading import tradingview_orchestrator as orch_mod

    orch = TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )
    symbols = [{"symbol": "ETH", "tradingview_symbol": "BINANCE:ETHUSDT", "rank": 1}]

    def boom(*_a, **_k):
        raise RuntimeError("redis exploded")

    fake_bus_module = type("M", (), {"publish": staticmethod(boom)})
    with patch.dict(
        "sys.modules", {"lib.core.event_bus": fake_bus_module}
    ), patch.object(
        orch, "screenshot",
        return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"},
    ), patch.object(
        orch, "probe_ohlcv", return_value={"ok": True}
    ), patch.object(
        orch, "probe_quote", return_value={"ok": True}
    ):
        # Must not raise.
        manifest = orch.capture_sweep(symbols, session_id="evt-test-failsafe")

    assert manifest["session_id"] == "evt-test-failsafe"
    assert (tmp_artifact_root / "evt-test-failsafe" / "manifest.json").exists()
    # Sanity: module-level constants still exposed for any caller wiring.
    assert orch_mod.EVENT_PINE_BATCH_COMPLETED == "tradingview.orchestrator.pine_batch_completed"


def test_event_name_constants_match_spec():
    assert EVENT_SESSION_COMPLETED == "tradingview.orchestrator.session_completed"
    assert EVENT_PINE_BATCH_COMPLETED == "tradingview.orchestrator.pine_batch_completed"


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
