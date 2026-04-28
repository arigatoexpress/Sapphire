"""Tests for the Sapphire signal_correlator plugin tool.

Covers:
- the dry-run path (no live bus) returns a CorrelatedSignal dict per pair
- caps and metadata are surfaced verbatim
- the rate limiter trips into a soft "rate_limited" outcome
- the ``status`` action does not contact sources
- the ``weights`` action exposes the resolved scoring config
- the ``latest`` action reads ``data/correlated_signals/<date>/signals.jsonl``
- the stdin JSON entry point matches Sapphire's tool contract
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "signal_correlator.py"

_spec = importlib.util.spec_from_file_location("signal_correlator_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
sc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sc
_spec.loader.exec_module(sc)


@pytest.fixture
def isolated_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "signal_correlator_cache"
    counter_path = cache_dir / "counters.json"
    output_root = tmp_path / "data" / "correlated_signals"
    output_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sc, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(sc, "COUNTER_PATH", counter_path)
    monkeypatch.setattr(sc, "DEFAULT_OUTPUT_ROOT", output_root)
    monkeypatch.delenv("SAPPHIRE_CORRELATOR_LIVE_BUS", raising=False)
    return cache_dir, output_root


class _StaticSource:
    name = "tradingview"

    def latest_for(self, symbol: str, timeframe: str) -> Any:
        from lib.correlator.sources import SourceSignal

        return SourceSignal(
            source="tradingview",
            symbol=symbol,
            timeframe=timeframe,
            direction="bull",
            confidence=0.7,
            age_seconds=60.0,
            timestamp_iso="2026-04-28T11:59:00+00:00",
            raw={},
        )


def test_correlate_once_returns_one_signal_per_pair(isolated_cache) -> None:
    out = sc.correlate_once_action(
        pairs=[("BTC", "1h"), ("ETH", "1h")],
        sources=[_StaticSource()],
    )
    assert out["ok"] is True
    assert len(out["signals"]) == 2
    syms = {s["symbol"] for s in out["signals"]}
    assert syms == {"BTC", "ETH"}


def test_correlate_once_metadata_includes_caps(isolated_cache) -> None:
    out = sc.correlate_once_action(
        pairs=[("BTC", "1h")],
        sources=[_StaticSource()],
    )
    caps = out["metadata"]["caps"]
    assert caps["max_sources_per_correlation"] == 16
    assert caps["max_correlations_per_hour"] == 1200
    assert caps["freshness_hard_limit_seconds"] == 86_400
    assert caps["edge_score_bound"] == [-1.0, 1.0]


def test_correlate_once_rate_limit_blocks(isolated_cache) -> None:
    cache_dir, _ = isolated_cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    counter_path = cache_dir / "counters.json"
    counter_path.write_text(
        json.dumps({"calls": [time.time()] * sc.MAX_CORRELATIONS_PER_HOUR, "lifetime_signals": 0}),
        encoding="utf-8",
    )
    out = sc.correlate_once_action(
        pairs=[("BTC", "1h")],
        sources=[_StaticSource()],
    )
    assert out["ok"] is False
    assert "rate_limit" in out["reason"]


def test_status_action_does_not_touch_sources(isolated_cache) -> None:
    snap = sc.status_action()
    assert snap["max_per_hour"] == sc.MAX_CORRELATIONS_PER_HOUR
    assert snap["live_bus_env"] is False
    assert snap["version"] == "0.1.0"


def test_weights_action_returns_defaults(isolated_cache, tmp_path) -> None:
    snap = sc.weights_action(weights_path=tmp_path / "absent.yaml")
    assert "tradingview" in snap["source_weights"]
    assert snap["config_exists"] is False
    assert snap["contradict_penalty"] >= 0.0


def test_weights_action_reads_yaml(isolated_cache, tmp_path) -> None:
    cfg = tmp_path / "weights.yaml"
    cfg.write_text(
        "source_weights:\n  tradingview: 9.0\nfreshness_half_life_seconds: 1800\n",
        encoding="utf-8",
    )
    snap = sc.weights_action(weights_path=cfg)
    assert snap["source_weights"]["tradingview"] == 9.0
    assert snap["freshness_half_life_seconds"] == 1800.0
    assert snap["config_exists"] is True


def test_latest_action_returns_rows(isolated_cache, monkeypatch) -> None:
    _, out_root = isolated_cache
    target_date = "2026-04-28"
    target_dir = out_root / target_date
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "signals.jsonl").write_text(
        json.dumps({"symbol": "BTC", "edge_score": 0.4, "consensus": "PARTIAL_BULL"}) + "\n",
        encoding="utf-8",
    )
    out = sc.latest_action(date=target_date)
    assert out["ok"] is True
    assert out["count"] == 1
    assert out["rows"][0]["symbol"] == "BTC"


def test_latest_action_returns_not_ok_when_missing(isolated_cache) -> None:
    out = sc.latest_action(date="1900-01-01")
    assert out["ok"] is False


def test_handle_unknown_action(isolated_cache) -> None:
    out = sc.handle({"action": "magic"})
    assert "error" in out
    assert "valid_actions" in out


def test_handle_invalid_pairs(isolated_cache) -> None:
    out = sc.handle({"action": "correlate-once", "pairs": "not-a-list"})
    assert "error" in out


def test_main_reads_stdin_and_writes_json(isolated_cache, monkeypatch) -> None:
    # Stub the source builder so the tool produces deterministic output.
    monkeypatch.setattr(sc, "build_default_sources", lambda: [_StaticSource()])

    out_buf = io.StringIO()
    rc = sc.main(
        stream_in=io.StringIO(json.dumps({"action": "correlate-once", "pairs": [["BTC", "1h"]]})),
        stream_out=out_buf,
    )
    assert rc == 0
    parsed = json.loads(out_buf.getvalue())
    assert parsed["ok"] is True
    assert parsed["signals"][0]["symbol"] == "BTC"


def test_main_rejects_invalid_json(isolated_cache) -> None:
    out_buf = io.StringIO()
    rc = sc.main(stream_in=io.StringIO("{not json"), stream_out=out_buf)
    assert rc == 2
    assert "invalid JSON" in out_buf.getvalue()


def test_main_rejects_non_object_payload(isolated_cache) -> None:
    out_buf = io.StringIO()
    rc = sc.main(stream_in=io.StringIO("[1,2,3]"), stream_out=out_buf)
    assert rc == 2


def test_correlate_once_live_bus_off_when_env_unset(isolated_cache, monkeypatch) -> None:
    """live_bus=true alone is not enough — env flag must also be set."""
    publishes: list[Any] = []

    class _Bus:
        def publish(self, *a, **k):
            publishes.append((a, k))
            return "x"

    import lib.core.event_bus as event_bus

    monkeypatch.setattr(event_bus, "get_bus", lambda *a, **k: _Bus())
    out = sc.correlate_once_action(
        pairs=[("BTC", "1h")],
        sources=[_StaticSource()],
        live_bus=True,
    )
    assert out["metadata"]["live_bus_actual"] is False
    assert publishes == []


def test_correlate_once_live_bus_on_when_env_and_request_set(
    isolated_cache, monkeypatch
) -> None:
    publishes: list[Any] = []

    class _Bus:
        def publish(self, *a, **k):
            publishes.append((a, k))
            return "x"

    import lib.core.event_bus as event_bus

    monkeypatch.setattr(event_bus, "get_bus", lambda *a, **k: _Bus())
    monkeypatch.setenv("SAPPHIRE_CORRELATOR_LIVE_BUS", "1")
    out = sc.correlate_once_action(
        pairs=[("BTC", "1h")],
        sources=[_StaticSource()],
        live_bus=True,
    )
    assert out["metadata"]["live_bus_actual"] is True
    assert len(publishes) == 1
