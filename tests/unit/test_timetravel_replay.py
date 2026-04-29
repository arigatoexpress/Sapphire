"""Unit tests for ``lib.timetravel.replay``.

The replay re-invokes :func:`lib.correlator.engine.correlate_once` and
:func:`lib.synthesis.narrative_engine.synthesize_thesis` on the
snapshot's correlated-signal rows. We mock both engines via
``monkeypatch`` to verify wiring (replay calls them with snapshot data
as input) and to assert provenance + ordering invariants.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Any

import pytest

from lib.correlator.engine import CorrelatedSignal
from lib.synthesis.narrative_engine import NarrativeThesis
from lib.timetravel.replay import ReplayResult, replay
from lib.timetravel.snapshot import SnapshotEntry, SystemSnapshot

replay_mod = importlib.import_module("lib.timetravel.replay")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _correlated_row(
    symbol: str,
    timeframe: str = "1h",
    *,
    edge: float = 0.42,
    consensus: str = "AGREE_BULL",
    bull: tuple[str, ...] = ("tradingview", "telegram"),
    bear: tuple[str, ...] = (),
    neutral: tuple[str, ...] = (),
    generated_at: str = "2026-04-26T10:00:00+00:00",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "edge_score": edge,
        "consensus": consensus,
        "contributing": len(bull) + len(bear) + len(neutral),
        "corroborated_by": list(bull),
        "divergent_sources": list(bear),
        "bull_sources": list(bull),
        "bear_sources": list(bear),
        "neutral_sources": list(neutral),
        "freshness_seconds": 60.0,
        "raw_score": edge,
        "agreement_multiplier": 1.05,
        "contradict_factor": 1.0,
        "total_weight": 0.8,
        "generated_at": generated_at,
    }


def _snapshot_with(rows: list[dict[str, Any]], *, at: str) -> SystemSnapshot:
    entry = SnapshotEntry(
        scope="correlated_signals",
        rows=tuple(rows),
        files_visited=("/fake/path.jsonl",),
        earliest_ts=at,
        latest_ts=at,
    )
    return SystemSnapshot(
        at=at,
        scope=("correlated_signals",),
        entries={"correlated_signals": entry},
        generated_at=at,
        index_signature="testsig",
        provenance_envelope={"generator": "test"},
    )


def _fake_correlated_signal(
    symbol: str = "BTC", timeframe: str = "1h", edge: float = 0.42
) -> CorrelatedSignal:
    return CorrelatedSignal(
        symbol=symbol,
        timeframe=timeframe,
        edge_score=edge,
        consensus="AGREE_BULL",
        corroborated_by=("tradingview", "telegram"),
        divergent_sources=(),
        bull_sources=("tradingview", "telegram"),
        bear_sources=(),
        neutral_sources=(),
        freshness_seconds=60.0,
        contributing=2,
        raw_score=edge,
        agreement_multiplier=1.05,
        contradict_factor=1.0,
        total_weight=0.8,
        generated_at="2026-04-26T10:00:00+00:00",
        provenance_envelope={"generator": "fake-correlator"},
    )


def _fake_thesis(symbol: str = "BTC", timeframe: str = "1h") -> NarrativeThesis:
    return NarrativeThesis(
        thesis_one_paragraph="fake thesis",
        evidence_bullets=["fake bullet"],
        counter_thesis_one_paragraph="fake counter",
        invalidators=["fake invalidator"],
        next_signal_to_watch="watch next",
        implied_position="long_mild",
        confidence=0.6,
        caveat_block="research only",
        provenance_envelope={"generator": "fake-narrative"},
        symbol=symbol,
        timeframe=timeframe,
        generated_at="2026-04-26T10:00:00+00:00",
        mode_actual="dry-run",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_replay_returns_replay_result_for_empty_snapshot() -> None:
    snap = _snapshot_with([], at="2026-04-26T10:00:00+00:00")
    result = replay(snap)
    assert isinstance(result, ReplayResult)
    assert result.correlated_signals == ()
    assert result.narratives == ()
    assert result.pairs_seen == ()


def test_replay_invokes_correlate_once_per_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_correlate(*, symbol, timeframe, signals_by_source, config, now):
        calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "sources": sorted(signals_by_source.keys()),
                "now": now,
            }
        )
        return _fake_correlated_signal(symbol, timeframe)

    monkeypatch.setattr(replay_mod, "correlate_once", fake_correlate)
    monkeypatch.setattr(
        replay_mod, "synthesize_thesis", lambda sig, **kw: _fake_thesis()
    )

    snap = _snapshot_with(
        [_correlated_row("BTC"), _correlated_row("ETH")],
        at="2026-04-26T10:30:00+00:00",
    )
    result = replay(snap)
    assert {(c["symbol"], c["timeframe"]) for c in calls} == {("BTC", "1h"), ("ETH", "1h")}
    assert len(result.correlated_signals) == 2


def test_replay_invokes_synthesize_thesis_per_correlated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_signals: list[Any] = []

    def fake_synth(sig, **kwargs):
        captured_signals.append(sig)
        return _fake_thesis()

    monkeypatch.setattr(replay_mod, "synthesize_thesis", fake_synth)
    monkeypatch.setattr(
        replay_mod,
        "correlate_once",
        lambda **kw: _fake_correlated_signal(kw["symbol"], kw["timeframe"]),
    )

    snap = _snapshot_with(
        [_correlated_row("BTC"), _correlated_row("SOL")],
        at="2026-04-26T10:30:00+00:00",
    )
    replay(snap)
    assert len(captured_signals) == 2


def test_replay_uses_snapshot_at_as_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nows: list[Any] = []

    def fake_correlate(*, symbol, timeframe, signals_by_source, config, now):
        nows.append(now)
        return _fake_correlated_signal(symbol, timeframe)

    monkeypatch.setattr(replay_mod, "correlate_once", fake_correlate)
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [_correlated_row("BTC")], at="2026-04-26T10:30:00+00:00"
    )
    replay(snap)
    assert all(now == datetime(2026, 4, 26, 10, 30, tzinfo=UTC) for now in nows)


def test_replay_reconstructs_source_signals_from_bull_bear_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_correlate(*, symbol, timeframe, signals_by_source, config, now):
        captured["sources_for_btc"] = signals_by_source if symbol == "BTC" else captured.get(
            "sources_for_btc"
        )
        return _fake_correlated_signal(symbol, timeframe)

    monkeypatch.setattr(replay_mod, "correlate_once", fake_correlate)
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [
            _correlated_row(
                "BTC",
                bull=("tradingview",),
                bear=("hyperliquid",),
                neutral=("telegram",),
            )
        ],
        at="2026-04-26T10:30:00+00:00",
    )
    replay(snap)
    assert set(captured["sources_for_btc"]) == {"tradingview", "hyperliquid", "telegram"}
    assert (
        captured["sources_for_btc"]["tradingview"]["direction"] == "bull"
    )
    assert captured["sources_for_btc"]["hyperliquid"]["direction"] == "bear"
    assert captured["sources_for_btc"]["telegram"]["direction"] == "neutral"


def test_replay_provenance_includes_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_mod,
        "correlate_once",
        lambda **kw: _fake_correlated_signal(kw["symbol"], kw["timeframe"]),
    )
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [_correlated_row("BTC")], at="2026-04-26T10:30:00+00:00"
    )
    result = replay(snap)
    env = result.provenance_envelope
    assert env["generator"] == "lib.timetravel.replay"
    assert "warning" in env and "research" in env["warning"]


def test_replay_records_pairs_and_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_mod,
        "correlate_once",
        lambda **kw: _fake_correlated_signal(kw["symbol"], kw["timeframe"]),
    )
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [
            _correlated_row(
                "BTC", bull=("tradingview",), bear=("hyperliquid",)
            ),
            _correlated_row("ETH", bull=("kronos",)),
        ],
        at="2026-04-26T10:30:00+00:00",
    )
    result = replay(snap)
    assert ("BTC", "1h") in result.pairs_seen
    assert ("ETH", "1h") in result.pairs_seen
    assert "tradingview" in result.sources_seen
    assert "kronos" in result.sources_seen
    assert "hyperliquid" in result.sources_seen


def test_replay_picks_latest_row_per_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_correlate(*, symbol, timeframe, signals_by_source, config, now):
        captured[(symbol, timeframe)] = signals_by_source
        return _fake_correlated_signal(symbol, timeframe)

    monkeypatch.setattr(replay_mod, "correlate_once", fake_correlate)
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [
            _correlated_row(
                "BTC",
                bull=("tradingview",),
                generated_at="2026-04-26T09:00:00+00:00",
            ),
            _correlated_row(
                "BTC",
                bull=("kronos",),
                generated_at="2026-04-26T10:00:00+00:00",
            ),
        ],
        at="2026-04-26T10:30:00+00:00",
    )
    replay(snap)
    sources = captured[("BTC", "1h")]
    # Latest row was the kronos-only one; tradingview should NOT be present.
    assert "kronos" in sources
    assert "tradingview" not in sources


def test_replay_handles_synthesize_thesis_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_mod,
        "correlate_once",
        lambda **kw: _fake_correlated_signal(kw["symbol"], kw["timeframe"]),
    )

    def boom(*a, **kw):
        raise RuntimeError("synthesizer broke")

    monkeypatch.setattr(replay_mod, "synthesize_thesis", boom)

    snap = _snapshot_with(
        [_correlated_row("BTC")], at="2026-04-26T10:30:00+00:00"
    )
    result = replay(snap)
    # Correlated signal still produced; narrative dropped.
    assert len(result.correlated_signals) == 1
    assert len(result.narratives) == 0


def test_replay_skips_rows_with_missing_symbol_or_timeframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_mod,
        "correlate_once",
        lambda **kw: _fake_correlated_signal(kw["symbol"], kw["timeframe"]),
    )
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [
            _correlated_row("BTC"),
            {"timeframe": "1h", "edge_score": 0.5, "generated_at": "2026-04-26T10:00:00+00:00"},
            {"symbol": "ETH", "edge_score": 0.5, "generated_at": "2026-04-26T10:00:00+00:00"},
        ],
        at="2026-04-26T10:30:00+00:00",
    )
    result = replay(snap)
    # Only BTC has both — others get filtered.
    assert {(s["symbol"], s["timeframe"]) for s in result.correlated_signals} == {("BTC", "1h")}


def test_replay_serializes_to_dict() -> None:
    snap = _snapshot_with([], at="2026-04-26T10:30:00+00:00")
    result = replay(snap)
    payload = result.to_dict()
    assert payload["at"] == "2026-04-26T10:30:00+00:00"
    assert payload["correlated_signals"] == []
    assert payload["narratives"] == []
    assert isinstance(payload["provenance_envelope"], dict)


def test_replay_age_seconds_non_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[Any, Any] = {}

    def fake_correlate(*, symbol, timeframe, signals_by_source, config, now):
        captured[symbol] = signals_by_source
        return _fake_correlated_signal(symbol, timeframe)

    monkeypatch.setattr(replay_mod, "correlate_once", fake_correlate)
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    # at is BEFORE the row generated_at — age should clamp to 0, not negative.
    snap = _snapshot_with(
        [_correlated_row("BTC", generated_at="2026-04-26T11:00:00+00:00")],
        at="2026-04-26T10:00:00+00:00",
    )
    replay(snap)
    for src in captured["BTC"].values():
        assert src["age_seconds"] >= 0.0


def test_replay_propagates_snapshot_index_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_mod,
        "correlate_once",
        lambda **kw: _fake_correlated_signal(kw["symbol"], kw["timeframe"]),
    )
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [_correlated_row("BTC")], at="2026-04-26T10:30:00+00:00"
    )
    result = replay(snap)
    assert result.snapshot_index_signature == "testsig"


def test_replay_at_string_round_trips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_mod,
        "correlate_once",
        lambda **kw: _fake_correlated_signal(kw["symbol"], kw["timeframe"]),
    )
    monkeypatch.setattr(replay_mod, "synthesize_thesis", lambda *a, **kw: _fake_thesis())

    snap = _snapshot_with(
        [_correlated_row("BTC")], at="2026-04-26T10:30:00+00:00"
    )
    result = replay(snap)
    assert result.at == "2026-04-26T10:30:00+00:00"


def test_replay_with_real_engines_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without monkeypatch, real correlator + synthesizer should run cleanly."""
    snap = _snapshot_with(
        [_correlated_row("BTC", bull=("tradingview", "telegram"))],
        at="2026-04-26T10:30:00+00:00",
    )
    result = replay(snap)
    assert len(result.correlated_signals) == 1
    assert len(result.narratives) == 1
    # Real synthesizer is deterministic dry-run by default.
    assert result.narratives[0]["mode_actual"] == "dry-run"
