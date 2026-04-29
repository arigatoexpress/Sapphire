"""Compare on-disk artifacts at time T vs. what current code would produce.

The diff surfaces drift on a small set of well-defined fields:

- correlated signals: ``edge_score``, ``consensus``, ``contributing``,
  ``corroborated_by`` (set delta), ``divergent_sources`` (set delta).
- narratives: ``implied_position``, ``confidence`` (numeric delta).

We do not diff free-text fields (``thesis_one_paragraph`` etc.) because
the dry-run synthesizer is deterministic — those should match exactly
when reasonable upstream data is present, but they're verbose and
unhelpful to highlight.

Public surface
--------------

- :class:`SignalDiff` — per ``(symbol, timeframe)`` drift record.
- :class:`DiffResult` — frozen aggregate diff between actual + replayed.
- :func:`diff_actual_vs_replay` — compute the diff. Pure function.

A row counts as ``unchanged`` only when *every* compared field matches
between actual and replay. Anything else is ``drifted``. Rows present
in only one side are ``actual_only`` or ``replay_only``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from lib.timetravel.replay import ReplayResult
from lib.timetravel.snapshot import SystemSnapshot

GENERATOR = "lib.timetravel.diff"
VERSION = "0.1.0"

# Numeric tolerance for edge_score/confidence comparison. Values smaller
# than this are treated as identical (floating-point noise).
NUMERIC_EPSILON = 1e-6

# When edge_score drifts by more than this we mark the row "high_drift".
HIGH_DRIFT_THRESHOLD = 0.05


@dataclass(frozen=True)
class SignalDiff:
    """Per ``(symbol, timeframe)`` drift report."""

    symbol: str
    timeframe: str
    status: str  # unchanged | drifted | actual_only | replay_only
    actual_edge: float | None = None
    replay_edge: float | None = None
    actual_consensus: str | None = None
    replay_consensus: str | None = None
    actual_contributing: int | None = None
    replay_contributing: int | None = None
    corroborated_set_delta: list[str] = field(default_factory=list)
    divergent_set_delta: list[str] = field(default_factory=list)
    narrative_position_actual: str | None = None
    narrative_position_replay: str | None = None
    narrative_confidence_delta: float | None = None
    high_drift: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiffResult:
    """Aggregate diff: per-pair drift + scope-level row counts."""

    at: str
    pairs: tuple[SignalDiff, ...]
    summary: dict[str, int]
    generated_at: str
    snapshot_index_signature: str
    provenance_envelope: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "pairs": [p.to_dict() for p in self.pairs],
            "summary": dict(self.summary),
            "generated_at": self.generated_at,
            "snapshot_index_signature": self.snapshot_index_signature,
            "provenance_envelope": dict(self.provenance_envelope),
        }


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("timeframe") or ""),
    )


def _index_by_pair(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = _key(row)
        if not key[0] or not key[1]:
            continue
        existing = out.get(key)
        # Keep the latest by generated_at, lexicographic over ISO strings.
        if existing is None or str(row.get("generated_at") or "") >= str(
            existing.get("generated_at") or ""
        ):
            out[key] = row
    return out


def _index_narratives(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        # On-disk narrative rows nest the actual thesis under "thesis".
        thesis = row.get("thesis") if isinstance(row.get("thesis"), dict) else row
        key = (
            str(thesis.get("symbol") or "").upper(),
            str(thesis.get("timeframe") or ""),
        )
        if not key[0] or not key[1]:
            continue
        existing = out.get(key)
        if existing is None or str(thesis.get("generated_at") or "") >= str(
            (existing.get("thesis") or existing).get("generated_at") or ""
        ):
            out[key] = row
    return out


def _set_diff(actual: Iterable[Any], replay: Iterable[Any]) -> list[str]:
    a = {str(item) for item in actual or ()}
    r = {str(item) for item in replay or ()}
    if a == r:
        return []
    diffs: list[str] = []
    for item in sorted(a - r):
        diffs.append(f"-{item}")
    for item in sorted(r - a):
        diffs.append(f"+{item}")
    return diffs


def _floats_close(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= NUMERIC_EPSILON


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compare(
    actual: dict[str, Any] | None,
    replay: dict[str, Any] | None,
    actual_narrative: dict[str, Any] | None,
    replay_narrative: dict[str, Any] | None,
    *,
    pair: tuple[str, str],
) -> SignalDiff:
    if actual is None and replay is None:
        return SignalDiff(
            symbol=pair[0], timeframe=pair[1], status="missing"
        )
    if actual is None:
        return _replay_only(replay, pair, replay_narrative)
    if replay is None:
        return _actual_only(actual, pair, actual_narrative)

    actual_edge = _safe_float(actual.get("edge_score"))
    replay_edge = _safe_float(replay.get("edge_score"))
    actual_consensus = str(actual.get("consensus") or "")
    replay_consensus = str(replay.get("consensus") or "")
    actual_contributing = _safe_int(actual.get("contributing"))
    replay_contributing = _safe_int(replay.get("contributing"))
    corroborated_delta = _set_diff(
        actual.get("corroborated_by") or (), replay.get("corroborated_by") or ()
    )
    divergent_delta = _set_diff(
        actual.get("divergent_sources") or (), replay.get("divergent_sources") or ()
    )

    narrative_position_actual: str | None = None
    narrative_position_replay: str | None = None
    confidence_delta: float | None = None
    if actual_narrative:
        narrative_position_actual = str(
            (actual_narrative.get("thesis") or actual_narrative).get("implied_position")
            or actual_narrative.get("implied_position")
            or ""
        )
    if replay_narrative:
        narrative_position_replay = str(replay_narrative.get("implied_position") or "")
    if actual_narrative and replay_narrative:
        a_conf = _safe_float(
            (actual_narrative.get("thesis") or actual_narrative).get("confidence")
            or actual_narrative.get("confidence")
        )
        r_conf = _safe_float(replay_narrative.get("confidence"))
        if a_conf is not None and r_conf is not None:
            confidence_delta = round(r_conf - a_conf, 6)

    edge_drift = (
        actual_edge is not None
        and replay_edge is not None
        and abs(replay_edge - actual_edge) > NUMERIC_EPSILON
    )
    consensus_drift = actual_consensus != replay_consensus
    contributing_drift = actual_contributing != replay_contributing
    set_drift = bool(corroborated_delta) or bool(divergent_delta)
    narrative_drift = (
        narrative_position_actual is not None
        and narrative_position_replay is not None
        and narrative_position_actual != narrative_position_replay
    ) or (confidence_delta is not None and abs(confidence_delta) > NUMERIC_EPSILON)
    drift = edge_drift or consensus_drift or contributing_drift or set_drift or narrative_drift
    status = "drifted" if drift else "unchanged"
    high_drift = (
        edge_drift
        and actual_edge is not None
        and replay_edge is not None
        and abs(replay_edge - actual_edge) > HIGH_DRIFT_THRESHOLD
    )
    return SignalDiff(
        symbol=pair[0],
        timeframe=pair[1],
        status=status,
        actual_edge=actual_edge,
        replay_edge=replay_edge,
        actual_consensus=actual_consensus or None,
        replay_consensus=replay_consensus or None,
        actual_contributing=actual_contributing,
        replay_contributing=replay_contributing,
        corroborated_set_delta=corroborated_delta,
        divergent_set_delta=divergent_delta,
        narrative_position_actual=narrative_position_actual,
        narrative_position_replay=narrative_position_replay,
        narrative_confidence_delta=confidence_delta,
        high_drift=high_drift,
    )


def _actual_only(
    actual: dict[str, Any],
    pair: tuple[str, str],
    actual_narrative: dict[str, Any] | None,
) -> SignalDiff:
    narrative_position = None
    if actual_narrative:
        narrative_position = str(
            (actual_narrative.get("thesis") or actual_narrative).get("implied_position")
            or actual_narrative.get("implied_position")
            or ""
        )
    return SignalDiff(
        symbol=pair[0],
        timeframe=pair[1],
        status="actual_only",
        actual_edge=_safe_float(actual.get("edge_score")),
        actual_consensus=str(actual.get("consensus") or "") or None,
        actual_contributing=_safe_int(actual.get("contributing")),
        narrative_position_actual=narrative_position,
    )


def _replay_only(
    replay: dict[str, Any],
    pair: tuple[str, str],
    replay_narrative: dict[str, Any] | None,
) -> SignalDiff:
    narrative_position = None
    if replay_narrative:
        narrative_position = str(replay_narrative.get("implied_position") or "")
    return SignalDiff(
        symbol=pair[0],
        timeframe=pair[1],
        status="replay_only",
        replay_edge=_safe_float(replay.get("edge_score")),
        replay_consensus=str(replay.get("consensus") or "") or None,
        replay_contributing=_safe_int(replay.get("contributing")),
        narrative_position_replay=narrative_position,
    )


def diff_actual_vs_replay(
    snapshot: SystemSnapshot,
    replay_result: ReplayResult,
    *,
    now: datetime | None = None,
) -> DiffResult:
    """Diff actual-at-T against replayed-at-T.

    Pure function — neither argument is mutated and no I/O happens.
    """
    if snapshot.at != replay_result.at:
        # Surface a soft mismatch in provenance instead of raising; the
        # diff is still computable, but the caller probably has a bug.
        pass

    actual_correlated = _index_by_pair(
        snapshot.by_scope("correlated_signals").rows
    )
    actual_narratives = _index_narratives(
        snapshot.by_scope("narratives").rows
    )
    replay_correlated = _index_by_pair(replay_result.correlated_signals)
    replay_narratives_idx: dict[tuple[str, str], dict[str, Any]] = {}
    for narr in replay_result.narratives:
        key = (
            str(narr.get("symbol") or "").upper(),
            str(narr.get("timeframe") or ""),
        )
        if key[0] and key[1]:
            replay_narratives_idx[key] = narr

    pairs = sorted(set(actual_correlated.keys()) | set(replay_correlated.keys()))
    diffs: list[SignalDiff] = []
    for pair in pairs:
        diffs.append(
            _compare(
                actual_correlated.get(pair),
                replay_correlated.get(pair),
                actual_narratives.get(pair),
                replay_narratives_idx.get(pair),
                pair=pair,
            )
        )

    summary = _summarize(diffs)
    generated_at = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    envelope = {
        "generator": GENERATOR,
        "version": VERSION,
        "at": snapshot.at,
        "snapshot_at": snapshot.at,
        "replay_at": replay_result.at,
        "snapshot_index_signature": snapshot.index_signature,
        "replay_index_signature": replay_result.snapshot_index_signature,
        "summary": summary,
        "generated_at": generated_at,
        "warning": (
            "Diff is research-only output. It surfaces drift between "
            "what was produced at the requested time and what current "
            "code would produce. It does not place trades."
        ),
    }
    return DiffResult(
        at=snapshot.at,
        pairs=tuple(diffs),
        summary=summary,
        generated_at=generated_at,
        snapshot_index_signature=snapshot.index_signature,
        provenance_envelope=envelope,
    )


def _summarize(diffs: list[SignalDiff]) -> dict[str, int]:
    counts = {
        "total": len(diffs),
        "unchanged": 0,
        "drifted": 0,
        "actual_only": 0,
        "replay_only": 0,
        "missing": 0,
        "high_drift": 0,
    }
    for diff in diffs:
        status = diff.status
        if status in counts:
            counts[status] += 1
        if diff.high_drift:
            counts["high_drift"] += 1
    return counts


__all__ = [
    "GENERATOR",
    "HIGH_DRIFT_THRESHOLD",
    "NUMERIC_EPSILON",
    "VERSION",
    "DiffResult",
    "SignalDiff",
    "diff_actual_vs_replay",
]
