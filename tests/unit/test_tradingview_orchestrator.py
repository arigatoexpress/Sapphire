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
    compute_quick_signal_score,
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


# ---------------------------------------------------------------------------
# compute_quick_signal_score: pure scoring of captured artifacts
# ---------------------------------------------------------------------------


def _ohlcv(open_: float, close: float, *, change_pct: str | None = None,
           last5: list[float] | None = None) -> dict:
    """Build a probe_ohlcv-shaped envelope for tests."""
    summary: dict = {"open": open_, "close": close, "high": max(open_, close), "low": min(open_, close)}
    if change_pct is not None:
        summary["change_pct"] = change_pct
    if last5 is not None:
        summary["last_5_bars"] = [{"close": c} for c in last5]
    return {"ok": True, "payload": summary}


def _values(rsi: float | None = None, macd_hist: float | None = None,
            ema: float | None = None) -> list[dict]:
    """Build a probe_values-shaped payload (list of {name, values})."""
    out = []
    if rsi is not None:
        out.append({"name": "RSI", "values": {"Plot": f"{rsi}"}})
    if macd_hist is not None:
        out.append({"name": "MACD", "values": {"Histogram": f"{macd_hist}"}})
    if ema is not None:
        out.append({"name": "Moving Average Exponential", "values": {"Plot": f"{ema}"}})
    return out


def test_score_returns_neutral_for_empty_inputs():
    res = compute_quick_signal_score({}, None)
    assert res["score"] == 0.0
    assert res["regime"] == "TRANSITION"
    assert "no scorable components" in res["rationale"]
    assert res["components"] == []


def test_score_strong_uptrend_full_stack():
    """Strong uptrend: RSI 75, MACD hist positive, price > EMA, +8% change."""
    ohlcv = _ohlcv(100.0, 108.0, change_pct="8.0%", last5=[100, 102, 104, 106, 108])
    values = _values(rsi=75.0, macd_hist=0.5, ema=104.0)
    res = compute_quick_signal_score({"payload": ohlcv["payload"]}, values)
    assert res["score"] > 0.4
    assert res["score"] <= 1.0
    assert res["regime"] == "RISK_ON"
    component_names = [c["name"] for c in res["components"]]
    assert "rsi" in component_names
    assert "macd" in component_names
    assert "ema" in component_names
    assert "change_pct" in component_names


def test_score_strong_downtrend_full_stack():
    ohlcv = _ohlcv(100.0, 92.0, change_pct="-8.0%", last5=[100, 98, 96, 94, 92])
    values = _values(rsi=25.0, macd_hist=-0.5, ema=96.0)
    res = compute_quick_signal_score({"payload": ohlcv["payload"]}, values)
    assert res["score"] < -0.4
    assert res["score"] >= -1.0
    assert res["regime"] == "RISK_OFF"


def test_score_flat_market_near_zero():
    ohlcv = _ohlcv(100.0, 100.1, change_pct="0.1%", last5=[100, 100.05, 100, 100.1, 100.1])
    values = _values(rsi=50.0, macd_hist=0.0, ema=100.0)
    res = compute_quick_signal_score(ohlcv, values)
    assert abs(res["score"]) < 0.05
    assert res["regime"] == "TRANSITION"


def test_score_clipped_to_unit_range():
    """Extreme values should clip to [-1, +1]."""
    ohlcv = _ohlcv(100.0, 200.0, change_pct="100%", last5=[100, 120, 140, 160, 200])
    values = _values(rsi=99.0, macd_hist=10.0, ema=100.0)
    res = compute_quick_signal_score(ohlcv, values)
    assert -1.0 <= res["score"] <= 1.0
    # Symmetric for downside.
    ohlcv_d = _ohlcv(200.0, 100.0, change_pct="-50%", last5=[200, 180, 160, 140, 100])
    values_d = _values(rsi=1.0, macd_hist=-10.0, ema=200.0)
    res_d = compute_quick_signal_score(ohlcv_d, values_d)
    assert -1.0 <= res_d["score"] <= 1.0


def test_score_handles_missing_indicator_values_gracefully():
    """Sweep mode: only OHLCV summary, no indicator_values payload."""
    ohlcv = _ohlcv(100.0, 105.0, change_pct="5.0%", last5=[100, 101, 103, 104, 105])
    res = compute_quick_signal_score(ohlcv, None)
    assert res["score"] > 0.0
    component_names = [c["name"] for c in res["components"]]
    assert component_names == ["change_pct", "trend5"]


def test_score_handles_partial_indicator_values():
    """If only RSI is captured, the scorer should still produce a result."""
    ohlcv = _ohlcv(100.0, 102.0, change_pct="2.0%", last5=[100, 101, 101.5, 102, 102])
    values = _values(rsi=70.0)  # no MACD, no EMA
    res = compute_quick_signal_score(ohlcv, values)
    assert res["score"] > 0.0
    component_names = [c["name"] for c in res["components"]]
    assert "rsi" in component_names
    assert "macd" not in component_names
    assert "ema" not in component_names


def test_score_ignores_garbage_values_payload():
    """Non-numeric / sentinel indicator values must not corrupt the score."""
    ohlcv = _ohlcv(100.0, 100.0, change_pct="0%")
    bad_values = [{"name": "RSI", "values": {"Plot": "∅"}}, {"name": "MACD", "values": {"Histogram": "n/a"}}]
    res = compute_quick_signal_score(ohlcv, bad_values)
    # No RSI/MACD components contributed.
    component_names = [c["name"] for c in res["components"]]
    assert "rsi" not in component_names
    assert "macd" not in component_names


def test_score_regime_thresholds_match_strategy_params():
    """Regime bucketing must use the canonical ±5% thresholds."""
    on = compute_quick_signal_score(_ohlcv(100, 105, change_pct="5.0%"), None)
    off = compute_quick_signal_score(_ohlcv(100, 95, change_pct="-5.0%"), None)
    mid = compute_quick_signal_score(_ohlcv(100, 102, change_pct="2.0%"), None)
    assert on["regime"] == "RISK_ON"
    assert off["regime"] == "RISK_OFF"
    assert mid["regime"] == "TRANSITION"


def test_score_unicode_minus_in_string_values():
    """tv values output sometimes uses unicode minus / percent signs."""
    ohlcv = _ohlcv(100.0, 95.0, change_pct="−5.0%")
    values = [{"name": "RSI", "values": {"Plot": "−10.5%"}}]  # invalid RSI but parseable
    res = compute_quick_signal_score(ohlcv, values)
    # change_pct must parse despite unicode minus.
    component_names = [c["name"] for c in res["components"]]
    assert "change_pct" in component_names
    assert res["score"] < 0.0


def test_score_deterministic_across_calls():
    """Same input → same output, byte-identical."""
    ohlcv = _ohlcv(100.0, 103.0, change_pct="3.0%", last5=[100, 101, 102, 102.5, 103])
    values = _values(rsi=60.0, macd_hist=0.1, ema=101.0)
    a = compute_quick_signal_score(ohlcv, values)
    b = compute_quick_signal_score(ohlcv, values)
    assert a == b


def test_capture_sweep_populates_score_per_symbol(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )
    symbols = [
        {"symbol": "ETH", "tradingview_symbol": "BINANCE:ETHUSDT", "rank": 1},
        {"symbol": "BTC", "tradingview_symbol": "BINANCE:BTCUSDT", "rank": 2},
    ]
    fake_ohlcv = {
        "ok": True,
        "payload": {
            "open": 100.0, "close": 105.0, "high": 106.0, "low": 99.0,
            "change_pct": "5.0%",
            "last_5_bars": [{"close": c} for c in [100, 101, 103, 104, 105]],
        },
    }
    with patch("lib.trading.tradingview_orchestrator._emit_event"), patch.object(
        orch, "screenshot",
        return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"},
    ), patch.object(orch, "probe_ohlcv", return_value=fake_ohlcv), patch.object(
        orch, "probe_quote", return_value={"ok": True}
    ):
        manifest = orch.capture_sweep(symbols, session_id="score-sweep")

    for sym in manifest["symbols"]:
        assert "score" in sym
        score = sym["score"]
        assert -1.0 <= score["score"] <= 1.0
        assert score["regime"] in {"RISK_ON", "TRANSITION", "RISK_OFF"}
        # Sweep does not capture indicator_values, so only fallbacks contribute.
        names = [c["name"] for c in score["components"]]
        assert names == ["change_pct", "trend5"]
        assert score["score"] > 0.0  # +5% is bullish

    # Persisted manifest must include the score field too.
    persisted = json.loads(
        (tmp_artifact_root / "score-sweep" / "manifest.json").read_text()
    )
    assert all("score" in s for s in persisted["symbols"])


def test_capture_symbol_deep_populates_score_per_timeframe(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_artifact_root,
        mutation_enabled=False,
    )
    fake_ohlcv = {
        "ok": True,
        "payload": {
            "open": 100.0, "close": 95.0, "high": 102.0, "low": 94.0,
            "change_pct": "-5.0%",
            "last_5_bars": [{"close": c} for c in [100, 99, 97, 96, 95]],
        },
    }
    fake_values = {
        "ok": True,
        "payload": [
            {"name": "RSI", "values": {"Plot": "30"}},
            {"name": "MACD", "values": {"Histogram": "-0.4"}},
        ],
    }
    with patch("lib.trading.tradingview_orchestrator._emit_event"), patch.object(
        orch, "screenshot",
        return_value={"ok": True, "path": "/tmp/fake.png", "filename": "fake.png"},
    ), patch.object(orch, "probe_ohlcv", return_value=fake_ohlcv), patch.object(
        orch, "probe_values", return_value=fake_values
    ), patch.object(orch, "probe_quote", return_value={"ok": True}):
        manifest = orch.capture_symbol_deep(
            "ETH", "BINANCE:ETHUSDT", timeframes=["60", "240"], session_id="score-deep"
        )

    assert len(manifest["timeframes"]) == 2
    for tf in manifest["timeframes"]:
        assert "score" in tf
        score = tf["score"]
        assert -1.0 <= score["score"] <= 1.0
        assert score["regime"] == "RISK_OFF"  # change_pct = -5%
        # Deep mode passes indicator_values, so RSI/MACD components are present.
        names = [c["name"] for c in score["components"]]
        assert "rsi" in names
        assert "macd" in names


def test_latest_scoring_sorts_by_abs_score(tmp_artifact_root: Path):
    """latest_scoring() must sort by |score| desc and respect top_n."""
    orch = TradingViewOrchestrator(tv_bin="echo", artifact_root=tmp_artifact_root)
    session = tmp_artifact_root / "20260101T000000Z"
    session.mkdir(parents=True)
    (session / "manifest.json").write_text(
        json.dumps({
            "generated_at": "2026-01-01T00:00:00+00:00",
            "schema_version": "tradingview-orchestrator.sweep_capture.v1",
            "session_id": "20260101T000000Z",
            "primary_timeframe": "60",
            "symbols": [
                {"symbol": "ETH", "tradingview_symbol": "BINANCE:ETHUSDT",
                 "score": {"score": 0.2, "regime": "TRANSITION", "rationale": "weak"}},
                {"symbol": "BTC", "tradingview_symbol": "BINANCE:BTCUSDT",
                 "score": {"score": -0.8, "regime": "RISK_OFF", "rationale": "strong bear"}},
                {"symbol": "SOL", "tradingview_symbol": "BINANCE:SOLUSDT",
                 "score": {"score": 0.5, "regime": "RISK_ON", "rationale": "strong bull"}},
            ],
        }),
        encoding="utf-8",
    )
    res = orch.latest_scoring()
    assert res["session_id"] == "20260101T000000Z"
    assert [r["symbol"] for r in res["items"]] == ["BTC", "SOL", "ETH"]
    assert res["items"][0]["score"] == -0.8
    res_top = orch.latest_scoring(top_n=2)
    assert [r["symbol"] for r in res_top["items"]] == ["BTC", "SOL"]


def test_latest_scoring_handles_no_manifest(tmp_artifact_root: Path):
    orch = TradingViewOrchestrator(tv_bin="echo", artifact_root=tmp_artifact_root)
    res = orch.latest_scoring()
    assert res["items"] == []
    assert res["session_id"] is None
