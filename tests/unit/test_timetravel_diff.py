"""Unit tests for ``lib.timetravel.diff``.

Coverage:

- unchanged when actual + replay match exactly,
- drifted when edge_score moves above the numeric epsilon,
- consensus drift,
- corroborated_by + divergent_sources set deltas,
- actual-only / replay-only,
- narrative position drift,
- narrative confidence delta,
- high_drift threshold,
- summary counts,
- diff serializes cleanly,
- pairs with missing ``symbol`` / ``timeframe`` are filtered out,
- empty inputs yield clean summary.
"""

from __future__ import annotations

from typing import Any

from lib.timetravel.diff import (
    HIGH_DRIFT_THRESHOLD,
    NUMERIC_EPSILON,
    diff_actual_vs_replay,
)
from lib.timetravel.replay import ReplayResult
from lib.timetravel.snapshot import SnapshotEntry, SystemSnapshot


def _correlated(
    symbol: str = "BTC",
    timeframe: str = "1h",
    edge: float = 0.42,
    consensus: str = "AGREE_BULL",
    bull: tuple[str, ...] = ("tradingview", "telegram"),
    bear: tuple[str, ...] = (),
    contributing: int = 2,
    generated_at: str = "2026-04-26T10:00:00+00:00",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "edge_score": edge,
        "consensus": consensus,
        "contributing": contributing,
        "corroborated_by": list(bull),
        "divergent_sources": list(bear),
        "bull_sources": list(bull),
        "bear_sources": list(bear),
        "generated_at": generated_at,
    }


def _narrative_row(
    symbol: str = "BTC",
    timeframe: str = "1h",
    *,
    position: str = "long_mild",
    confidence: float = 0.55,
    generated_at: str = "2026-04-26T10:00:00+00:00",
) -> dict[str, Any]:
    return {
        "thesis": {
            "symbol": symbol,
            "timeframe": timeframe,
            "implied_position": position,
            "confidence": confidence,
            "generated_at": generated_at,
        }
    }


def _replayed_narrative(
    symbol: str = "BTC",
    timeframe: str = "1h",
    *,
    position: str = "long_mild",
    confidence: float = 0.55,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "implied_position": position,
        "confidence": confidence,
    }


def _make_snapshot(
    correlated: list[dict[str, Any]] | None = None,
    narratives: list[dict[str, Any]] | None = None,
    *,
    at: str = "2026-04-26T10:30:00+00:00",
) -> SystemSnapshot:
    entries = {
        "correlated_signals": SnapshotEntry(
            scope="correlated_signals", rows=tuple(correlated or [])
        ),
        "narratives": SnapshotEntry(scope="narratives", rows=tuple(narratives or [])),
    }
    return SystemSnapshot(
        at=at,
        scope=("correlated_signals", "narratives"),
        entries=entries,
        generated_at=at,
        index_signature="testsig",
        provenance_envelope={"generator": "test"},
    )


def _make_replay(
    correlated: list[dict[str, Any]] | None = None,
    narratives: list[dict[str, Any]] | None = None,
    *,
    at: str = "2026-04-26T10:30:00+00:00",
) -> ReplayResult:
    return ReplayResult(
        at=at,
        correlated_signals=tuple(correlated or []),
        narratives=tuple(narratives or []),
        pairs_seen=(),
        sources_seen=(),
        generated_at=at,
        snapshot_index_signature="testsig",
        provenance_envelope={},
    )


def test_unchanged_when_actual_and_replay_match() -> None:
    snap = _make_snapshot(
        correlated=[_correlated()],
        narratives=[_narrative_row()],
    )
    rep = _make_replay(correlated=[_correlated()], narratives=[_replayed_narrative()])
    diff = diff_actual_vs_replay(snap, rep)
    assert diff.summary["unchanged"] == 1
    assert diff.summary["drifted"] == 0
    assert diff.summary["high_drift"] == 0


def test_edge_score_drift_above_epsilon() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(edge=0.42)],
        narratives=[_narrative_row()],
    )
    rep = _make_replay(
        correlated=[_correlated(edge=0.50)],
        narratives=[_replayed_narrative()],
    )
    diff = diff_actual_vs_replay(snap, rep)
    assert diff.summary["drifted"] == 1
    pair = diff.pairs[0]
    assert pair.actual_edge == 0.42
    assert pair.replay_edge == 0.50
    assert pair.high_drift is True


def test_consensus_drift() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(consensus="AGREE_BULL")],
    )
    rep = _make_replay(
        correlated=[_correlated(consensus="CONTRADICT")],
    )
    diff = diff_actual_vs_replay(snap, rep)
    pair = diff.pairs[0]
    assert pair.status == "drifted"
    assert pair.actual_consensus == "AGREE_BULL"
    assert pair.replay_consensus == "CONTRADICT"


def test_corroborated_by_set_delta() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(bull=("tradingview", "telegram"))],
    )
    rep = _make_replay(
        correlated=[_correlated(bull=("tradingview", "kronos"))],
    )
    diff = diff_actual_vs_replay(snap, rep)
    pair = diff.pairs[0]
    delta = pair.corroborated_set_delta
    assert "-telegram" in delta
    assert "+kronos" in delta


def test_divergent_set_delta() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(bull=("tradingview",), bear=("hyperliquid",))],
    )
    rep = _make_replay(
        correlated=[_correlated(bull=("tradingview",), bear=("hyperliquid", "telegram"))],
    )
    diff = diff_actual_vs_replay(snap, rep)
    delta = diff.pairs[0].divergent_set_delta
    assert "+telegram" in delta


def test_actual_only_pair() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(symbol="BTC"), _correlated(symbol="ETH")],
    )
    rep = _make_replay(
        correlated=[_correlated(symbol="BTC")],
    )
    diff = diff_actual_vs_replay(snap, rep)
    statuses = {(p.symbol, p.status) for p in diff.pairs}
    assert ("ETH", "actual_only") in statuses


def test_replay_only_pair() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(symbol="BTC")],
    )
    rep = _make_replay(
        correlated=[_correlated(symbol="BTC"), _correlated(symbol="SOL")],
    )
    diff = diff_actual_vs_replay(snap, rep)
    statuses = {(p.symbol, p.status) for p in diff.pairs}
    assert ("SOL", "replay_only") in statuses


def test_narrative_position_drift() -> None:
    snap = _make_snapshot(
        correlated=[_correlated()],
        narratives=[_narrative_row(position="long_strong")],
    )
    rep = _make_replay(
        correlated=[_correlated()],
        narratives=[_replayed_narrative(position="long_mild")],
    )
    diff = diff_actual_vs_replay(snap, rep)
    pair = diff.pairs[0]
    assert pair.status == "drifted"
    assert pair.narrative_position_actual == "long_strong"
    assert pair.narrative_position_replay == "long_mild"


def test_narrative_confidence_delta() -> None:
    snap = _make_snapshot(
        correlated=[_correlated()],
        narratives=[_narrative_row(confidence=0.50)],
    )
    rep = _make_replay(
        correlated=[_correlated()],
        narratives=[_replayed_narrative(confidence=0.65)],
    )
    diff = diff_actual_vs_replay(snap, rep)
    delta = diff.pairs[0].narrative_confidence_delta
    assert delta is not None
    assert abs(delta - 0.15) < 1e-6


def test_high_drift_threshold() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(edge=0.10)],
        narratives=[_narrative_row()],
    )
    rep = _make_replay(
        correlated=[_correlated(edge=0.10 + HIGH_DRIFT_THRESHOLD + 0.01)],
        narratives=[_replayed_narrative()],
    )
    diff = diff_actual_vs_replay(snap, rep)
    assert diff.summary["high_drift"] == 1
    assert diff.pairs[0].high_drift is True


def test_below_high_drift_does_not_set_flag() -> None:
    snap = _make_snapshot(correlated=[_correlated(edge=0.10)])
    rep = _make_replay(correlated=[_correlated(edge=0.10 + HIGH_DRIFT_THRESHOLD - 0.001)])
    diff = diff_actual_vs_replay(snap, rep)
    assert diff.pairs[0].high_drift is False
    # But the row IS still drifted (above the numeric epsilon).
    assert diff.pairs[0].status == "drifted"


def test_summary_counts_match_diffs() -> None:
    snap = _make_snapshot(
        correlated=[
            _correlated(symbol="BTC"),
            _correlated(symbol="ETH", edge=0.42),
            _correlated(symbol="LINK"),  # actual_only
        ],
    )
    rep = _make_replay(
        correlated=[
            _correlated(symbol="BTC"),  # unchanged
            _correlated(symbol="ETH", edge=0.50),  # drifted
            _correlated(symbol="SOL"),  # replay_only
        ],
    )
    diff = diff_actual_vs_replay(snap, rep)
    summary = diff.summary
    assert summary["total"] == 4  # BTC, ETH, LINK, SOL
    assert summary["unchanged"] == 1
    assert summary["drifted"] == 1
    assert summary["actual_only"] == 1
    assert summary["replay_only"] == 1


def test_diff_serializes_to_dict() -> None:
    snap = _make_snapshot(correlated=[_correlated()], narratives=[_narrative_row()])
    rep = _make_replay(correlated=[_correlated()], narratives=[_replayed_narrative()])
    diff = diff_actual_vs_replay(snap, rep)
    payload = diff.to_dict()
    assert payload["at"] == "2026-04-26T10:30:00+00:00"
    assert isinstance(payload["pairs"], list)
    assert isinstance(payload["summary"], dict)
    assert isinstance(payload["provenance_envelope"], dict)


def test_pairs_missing_symbol_or_timeframe_are_filtered() -> None:
    snap = _make_snapshot(
        correlated=[
            _correlated(symbol="BTC"),
            {"timeframe": "1h", "edge_score": 0.4},  # no symbol
        ],
    )
    rep = _make_replay(correlated=[_correlated(symbol="BTC")])
    diff = diff_actual_vs_replay(snap, rep)
    # Only BTC should be diff'd.
    assert all(p.symbol for p in diff.pairs)


def test_empty_inputs_yield_zero_summary() -> None:
    snap = _make_snapshot(correlated=[])
    rep = _make_replay(correlated=[])
    diff = diff_actual_vs_replay(snap, rep)
    assert diff.summary["total"] == 0
    assert diff.pairs == ()


def test_small_floating_point_noise_below_epsilon_is_unchanged() -> None:
    snap = _make_snapshot(
        correlated=[_correlated(edge=0.42)],
        narratives=[_narrative_row()],
    )
    rep = _make_replay(
        correlated=[_correlated(edge=0.42 + NUMERIC_EPSILON / 10.0)],
        narratives=[_replayed_narrative()],
    )
    diff = diff_actual_vs_replay(snap, rep)
    assert diff.pairs[0].status == "unchanged"
