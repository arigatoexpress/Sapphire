"""Tests for ``services.correlator.run`` daemon harness.

We do not exercise the LaunchAgent loop in real time. The interesting
behaviour is:

- ``run_once`` writes a JSONL + envelope sidecar and returns counts.
- Provenance envelope is emitted next to every JSONL.
- Rate-limit refusal is soft (returns ``ok: False``).
- Live-bus publish is gated by ``SAPPHIRE_CORRELATOR_LIVE_BUS=1``.
- ``daemon`` honours ``max_iterations`` for tests.
- ``status`` is read-only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lib.correlator import CorrelatorConfig
from lib.correlator.scoring import ScoringWeights
from lib.correlator.sources import SourceSignal
from services.correlator import run as runner

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)


class _StaticSource:
    name = "tradingview"

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
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


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    out_root = tmp_path / "data" / "correlated_signals"
    cache_dir = tmp_path / "cache"
    out_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "DEFAULT_OUTPUT_ROOT", out_root)
    monkeypatch.setattr(runner, "DEFAULT_CACHE_DIR", cache_dir)
    monkeypatch.delenv("SAPPHIRE_CORRELATOR_LIVE_BUS", raising=False)
    return out_root, cache_dir


def test_run_once_writes_jsonl_and_envelope(isolated) -> None:
    out_root, _ = isolated
    config = CorrelatorConfig(weights=ScoringWeights())
    result = runner.run_once(
        universe=[("BTC", "1h"), ("ETH", "1h")],
        sources=[_StaticSource()],
        config=config,
        output_root=out_root,
        cache_dir=out_root.parent / "cache",
        now=FROZEN_NOW,
        publish=False,
    )
    assert result["ok"] is True
    assert result["expected"] == 2
    assert result["emitted"] == 2

    jsonl_path = Path(result["jsonl_path"])
    envelope_path = Path(result["envelope_path"])
    assert jsonl_path.exists()
    assert envelope_path.exists()

    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {r["symbol"] for r in rows} == {"BTC", "ETH"}
    assert all(r["consensus"] == "PARTIAL_BULL" for r in rows)

    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert envelope["generator"] == "services.correlator.run"
    assert envelope["version"] == "0.1.0"
    assert envelope["signals_appended"] == 2
    assert envelope["expires_at"]


def test_run_once_appends_to_existing_file(isolated) -> None:
    out_root, _ = isolated
    runner.run_once(
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=out_root.parent / "cache",
        now=FROZEN_NOW,
        publish=False,
    )
    runner.run_once(
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=out_root.parent / "cache",
        now=FROZEN_NOW,
        publish=False,
    )
    jsonl_path = runner._output_path(out_root, now=FROZEN_NOW)
    rows = [line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2


def test_run_once_emits_a_signal_with_provenance(isolated) -> None:
    out_root, _ = isolated
    result = runner.run_once(
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=out_root.parent / "cache",
        now=FROZEN_NOW,
        publish=False,
    )
    jsonl_path = Path(result["jsonl_path"])
    row = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert "provenance_envelope" in row
    assert row["provenance_envelope"]["generator"] == "lib.correlator.engine"


def test_run_once_rate_limit_blocks_excess(isolated, monkeypatch) -> None:
    out_root, cache_dir = isolated
    # Force the rate counter to be saturated before we start.
    counters_path = cache_dir / "counters.json"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import time as _t

    counters_path.write_text(
        json.dumps({"emissions": [_t.time()] * runner.MAX_CORRELATIONS_PER_HOUR, "lifetime": 0}),
        encoding="utf-8",
    )
    result = runner.run_once(
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=cache_dir,
        rate_limit_per_hour=runner.MAX_CORRELATIONS_PER_HOUR,
        now=FROZEN_NOW,
        publish=False,
    )
    assert result["ok"] is False
    assert "rate_limit" in result["reason"]


def test_run_once_live_bus_gate_off_by_default(isolated, monkeypatch) -> None:
    out_root, cache_dir = isolated
    published: list[tuple[str, dict]] = []

    class _FakeBus:
        def publish(self, event_type, data, source=None):
            published.append((event_type, data))
            return "id-1"

    def _get_bus(source: str) -> _FakeBus:  # pragma: no cover - never called
        return _FakeBus()

    # If live-bus is disabled (default), the bus must not be touched.
    import lib.core.event_bus as event_bus

    monkeypatch.setattr(event_bus, "get_bus", _get_bus)

    runner.run_once(
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=cache_dir,
        now=FROZEN_NOW,
        publish=True,  # respect the gate, not this flag
    )
    assert published == []


def test_run_once_live_bus_publishes_when_enabled(isolated, monkeypatch) -> None:
    out_root, cache_dir = isolated
    published: list[tuple[str, dict]] = []

    class _FakeBus:
        def publish(self, event_type, data, source=None):
            published.append((event_type, data))
            return "id-1"

    import lib.core.event_bus as event_bus

    monkeypatch.setattr(event_bus, "get_bus", lambda *a, **k: _FakeBus())
    monkeypatch.setenv("SAPPHIRE_CORRELATOR_LIVE_BUS", "1")

    runner.run_once(
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=cache_dir,
        now=FROZEN_NOW,
        publish=True,
    )
    assert len(published) == 1
    assert published[0][0] == "signal.correlated"


def test_daemon_respects_max_iterations(isolated) -> None:
    out_root, cache_dir = isolated
    sleeps: list[float] = []

    def _record_sleep(s: float) -> None:
        sleeps.append(s)

    res = runner.daemon(
        poll_interval_seconds=0.0,
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=cache_dir,
        max_iterations=2,
        sleep=_record_sleep,
    )
    assert res["iterations"] == 2
    # max_iterations=N implies (N-1) sleeps.
    assert len(sleeps) == 1


def test_status_is_read_only(isolated) -> None:
    out_root, cache_dir = isolated
    runner.run_once(
        universe=[("BTC", "1h")],
        sources=[_StaticSource()],
        output_root=out_root,
        cache_dir=cache_dir,
        now=FROZEN_NOW,
        publish=False,
    )
    snap = runner.status(cache_dir=cache_dir)
    assert snap["max_per_hour"] == runner.MAX_CORRELATIONS_PER_HOUR
    assert snap["live_bus"] is False
    assert snap["lifetime_emissions"] >= 1
