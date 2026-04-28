"""Tests for the narrative synthesis service runner."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from services.synthesis import run as runner

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)


def _signal(edge: float = 0.72, symbol: str = "BTC") -> dict:
    return {
        "symbol": symbol,
        "timeframe": "1h",
        "edge_score": edge,
        "consensus": "AGREE_BULL" if edge > 0 else "AGREE_BEAR",
        "corroborated_by": ["tradingview", "kronos_forecast"],
        "divergent_sources": [],
        "bull_sources": ["tradingview", "kronos_forecast"] if edge > 0 else [],
        "bear_sources": ["hyperliquid", "ta_scanner"] if edge < 0 else [],
        "neutral_sources": [],
        "freshness_seconds": 60,
        "contributing": 3,
        "raw_score": edge,
        "agreement_multiplier": 1.2,
        "contradict_factor": 1.0,
        "total_weight": 3.0,
        "generated_at": "2026-04-28T11:59:00+00:00",
        "provenance_envelope": {"generator": "lib.correlator.engine"},
    }


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    input_root = tmp_path / "correlated"
    output_root = tmp_path / "narratives"
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(runner, "DEFAULT_CORRELATOR_ROOT", input_root)
    monkeypatch.setattr(runner, "DEFAULT_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(runner, "DEFAULT_CACHE_DIR", cache_dir)
    monkeypatch.delenv("SAPPHIRE_NARRATIVE_LIVE_BUS", raising=False)
    return input_root, output_root, cache_dir


def test_run_once_writes_publishable_jsonl_and_envelope(isolated) -> None:
    input_root, output_root, cache_dir = isolated
    result = runner.run_once(
        input_root=input_root,
        output_root=output_root,
        cache_dir=cache_dir,
        signals=[_signal()],
        now=FROZEN_NOW,
        publish=False,
    )
    assert result["published_rows"] == 1
    path = Path(result["output_path"])
    assert path.exists()
    assert path.with_name("theses.jsonl.envelope.json").exists()
    row = json.loads(path.read_text().splitlines()[0])
    assert row["symbol"] == "BTC"
    assert row["rubric"]["publishable"] is True


def test_run_once_skips_when_edge_delta_is_small(isolated) -> None:
    input_root, output_root, cache_dir = isolated
    runner.run_once(
        input_root=input_root,
        output_root=output_root,
        cache_dir=cache_dir,
        signals=[_signal(0.50)],
        now=FROZEN_NOW,
        publish=False,
    )
    result = runner.run_once(
        input_root=input_root,
        output_root=output_root,
        cache_dir=cache_dir,
        signals=[_signal(0.55)],
        now=FROZEN_NOW,
        publish=False,
    )
    assert result["signals_changed"] == 0
    assert result["published_rows"] == 0


def test_run_once_selects_edge_delta_above_threshold(isolated) -> None:
    input_root, output_root, cache_dir = isolated
    runner.run_once(
        input_root=input_root,
        output_root=output_root,
        cache_dir=cache_dir,
        signals=[_signal(0.50)],
        now=FROZEN_NOW,
        publish=False,
    )
    result = runner.run_once(
        input_root=input_root,
        output_root=output_root,
        cache_dir=cache_dir,
        signals=[_signal(0.70)],
        now=FROZEN_NOW,
        publish=False,
    )
    assert result["signals_changed"] == 1


def test_latest_signal_rows_returns_latest_per_pair(isolated) -> None:
    input_root, _, _ = isolated
    path = input_root / "2026-04-28" / "signals.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(_signal(0.2)) + "\n" + json.dumps(_signal(0.4)) + "\n",
        encoding="utf-8",
    )
    rows = runner.latest_signal_rows(input_root=input_root, date="2026-04-28")
    assert len(rows) == 1
    assert rows[0]["edge_score"] == 0.4


def test_live_bus_gate_off_by_default(isolated, monkeypatch) -> None:
    published: list[tuple[str, dict]] = []

    class _Bus:
        def publish(self, *args, **_kwargs):
            published.append(args)

    import lib.core.event_bus as event_bus

    monkeypatch.setattr(event_bus, "get_bus", lambda *a, **k: _Bus())
    runner.run_once(signals=[_signal()], output_root=isolated[1], cache_dir=isolated[2])
    assert published == []


def test_live_bus_publishes_when_enabled(isolated, monkeypatch) -> None:
    published: list[tuple[str, dict]] = []

    class _Bus:
        def publish(self, *args, **_kwargs):
            published.append(args)

    import lib.core.event_bus as event_bus

    monkeypatch.setattr(event_bus, "get_bus", lambda *a, **k: _Bus())
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE_BUS", "1")
    result = runner.run_once(signals=[_signal()], output_root=isolated[1], cache_dir=isolated[2])
    assert result["event_bus_published"] == 1
    assert published[0][0] == "narrative.thesis.generated"


def test_daemon_respects_max_iterations(isolated) -> None:
    sleeps: list[float] = []
    result = runner.daemon(
        poll_interval_seconds=0,
        max_iterations=2,
        sleep=lambda value: sleeps.append(value),
        signals=[_signal()],
        output_root=isolated[1],
        cache_dir=isolated[2],
    )
    assert result["iterations"] == 2


def test_status_is_read_only(isolated) -> None:
    snap = runner.status(cache_dir=isolated[2])
    assert snap["tracked_pairs"] == 0
    assert snap["default_edge_delta"] == 0.10
