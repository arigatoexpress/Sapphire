"""Replay a :class:`SystemSnapshot` through the current correlator and
narrative engine.

The result represents *what current code would produce given a frozen
view of the time series*. It never overwrites artifacts under
``data/`` and never publishes to the event bus. The replay is a pure
function of the snapshot rows and the engines' current behaviour.

Public surface
--------------

- :class:`ReplayResult` — frozen dataclass packaging replayed
  correlated signals, replayed narratives, and provenance.
- :func:`replay` — the entrypoint. Takes a :class:`SystemSnapshot`
  and returns a :class:`ReplayResult`.

The replay is deliberately conservative:

- We rebuild a per-source ``SourceSignal`` from the *latest pre-``at``*
  row keyed by ``(symbol, timeframe)`` for each source name observed
  in the snapshot's ``correlated_signals`` scope.
- We then re-invoke :func:`lib.correlator.engine.correlate_once` for
  every ``(symbol, timeframe)`` we saw, *as if right now were ``at``*.
- For each replayed correlated signal we synthesize a narrative thesis
  in dry-run mode via :func:`lib.synthesis.narrative_engine.synthesize_thesis`.
  The synthesizer's offline branch is fully deterministic.

Why we don't re-run macro/cross-asset/on-chain pipelines
--------------------------------------------------------

The correlator engine reads pre-summarized rows; the upstream macro,
cross-asset and on-chain pipelines persist their summaries to disk
(``data/macro/...`` etc.) which the snapshot already captured. Replay
exercises the *fusion* layer that combines those rows. Re-running the
full upstream pipelines would require live network access and is out
of scope for a research-only time-travel surface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from lib.correlator.engine import (
    CorrelatedSignal,
    CorrelatorConfig,
    correlate_once,
)
from lib.correlator.sources import SourceSignal
from lib.synthesis.narrative_engine import (
    NarrativeThesis,
    synthesize_thesis,
)
from lib.timetravel.snapshot import SystemSnapshot

log = logging.getLogger(__name__)

GENERATOR = "lib.timetravel.replay"
VERSION = "0.1.0"


@dataclass(frozen=True)
class ReplayResult:
    """Result of replaying a snapshot through current code."""

    at: str
    correlated_signals: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    narratives: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    pairs_seen: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    sources_seen: tuple[str, ...] = field(default_factory=tuple)
    generated_at: str = ""
    snapshot_index_signature: str = ""
    provenance_envelope: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "correlated_signals": list(self.correlated_signals),
            "narratives": list(self.narratives),
            "pairs_seen": [list(p) for p in self.pairs_seen],
            "sources_seen": list(self.sources_seen),
            "generated_at": self.generated_at,
            "snapshot_index_signature": self.snapshot_index_signature,
            "provenance_envelope": dict(self.provenance_envelope),
        }


def _row_age_seconds(row_generated_at: Any, at: datetime) -> float:
    if not row_generated_at:
        return 0.0
    try:
        s = str(row_generated_at)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        ts = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = (at - ts.astimezone(UTC)).total_seconds()
    return float(max(delta, 0.0))


def _coerce_at(at: str) -> datetime:
    s = str(at or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(s) if s else datetime.now(UTC)
    except ValueError:
        return datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _direction_from_correlated_row(row: dict[str, Any], source: str) -> str:
    bull = row.get("bull_sources") or ()
    bear = row.get("bear_sources") or ()
    if source in tuple(bull):
        return "bull"
    if source in tuple(bear):
        return "bear"
    return "neutral"


def _confidence_from_correlated_row(row: dict[str, Any]) -> float:
    """Use the absolute edge_score as a per-source confidence proxy."""
    try:
        return abs(float(row.get("edge_score") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _reconstruct_source_signals(
    rows: tuple[dict[str, Any], ...],
    at: datetime,
) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    """Build ``{(symbol, timeframe): {source_name: SourceSignal-dict}}``.

    For each ``(symbol, timeframe)`` we take the latest pre-``at`` row
    and one ``SourceSignal`` per name in ``corroborated_by`` (and the
    bull/bear/neutral split). Direction is derived from which bucket
    the source appears in. Confidence is the absolute edge score.

    Replay runs ``correlate_once`` against this reconstruction and we
    expect a result that mirrors the original row when the engine's
    behaviour hasn't drifted.
    """
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        tf = str(row.get("timeframe") or "")
        if not sym or not tf:
            continue
        key = (sym, tf)
        existing = by_pair.get(key)
        existing_ts = existing.get("generated_at") if existing else ""
        if not existing or str(row.get("generated_at") or "") >= str(existing_ts or ""):
            by_pair[key] = row

    out: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for (sym, tf), row in by_pair.items():
        sources: dict[str, dict[str, Any]] = {}
        seen_sources: set[str] = set()
        for src in row.get("bull_sources") or ():
            seen_sources.add(str(src))
        for src in row.get("bear_sources") or ():
            seen_sources.add(str(src))
        for src in row.get("neutral_sources") or ():
            seen_sources.add(str(src))
        if not seen_sources:
            for src in row.get("corroborated_by") or ():
                seen_sources.add(str(src))
        confidence = _confidence_from_correlated_row(row)
        for src in seen_sources:
            direction = _direction_from_correlated_row(row, src)
            sources[src] = SourceSignal(
                source=src,
                symbol=sym,
                timeframe=tf,
                direction=direction,
                confidence=round(min(1.0, max(0.0, confidence)), 4),
                age_seconds=_row_age_seconds(row.get("generated_at"), at),
                timestamp_iso=str(row.get("generated_at") or at.isoformat()),
                raw={"replay": True, "source_row_at": row.get("generated_at")},
            ).to_dict()
        out[(sym, tf)] = sources
    return out


def _replay_correlations(
    snapshot: SystemSnapshot,
    *,
    config: CorrelatorConfig | None = None,
) -> tuple[
    list[CorrelatedSignal], list[tuple[str, str]], list[str], dict[tuple[str, str], dict[str, Any]]
]:
    """Run :func:`correlate_once` for each pair seen in the snapshot."""
    config = config or CorrelatorConfig()
    at = _coerce_at(snapshot.at)
    correlated_rows = snapshot.by_scope("correlated_signals").rows
    reconstructed = _reconstruct_source_signals(correlated_rows, at)
    sources_seen: set[str] = set()
    out: list[CorrelatedSignal] = []
    pairs_seen: list[tuple[str, str]] = []
    pair_to_source_dict: dict[tuple[str, str], dict[str, Any]] = {}
    for (sym, tf), sources in sorted(reconstructed.items()):
        sources_seen.update(sources.keys())
        replayed = correlate_once(
            symbol=sym,
            timeframe=tf,
            signals_by_source=sources,
            config=config,
            now=at,
        )
        out.append(replayed)
        pairs_seen.append((sym, tf))
        pair_to_source_dict[(sym, tf)] = sources
    return out, pairs_seen, sorted(sources_seen), pair_to_source_dict


def _replay_narratives(
    correlated: list[CorrelatedSignal],
    *,
    at: datetime,
) -> list[NarrativeThesis]:
    """Synthesize a deterministic dry-run thesis per replayed signal."""
    out: list[NarrativeThesis] = []
    for sig in correlated:
        try:
            thesis = synthesize_thesis(sig.to_dict(), mode="dry-run", now=at)
        except Exception as exc:  # noqa: BLE001 - replay never raises.
            log.warning(
                "narrative replay failed for %s/%s: %s",
                sig.symbol,
                sig.timeframe,
                exc,
            )
            continue
        out.append(thesis)
    return out


def replay(
    snapshot: SystemSnapshot,
    *,
    config: CorrelatorConfig | None = None,
    now: datetime | None = None,
) -> ReplayResult:
    """Re-run the correlator + narrative engine against ``snapshot``.

    Returns a :class:`ReplayResult` with the same shape as the on-disk
    artifacts so callers can run :func:`lib.timetravel.diff.diff_actual_vs_replay`.
    """
    at = _coerce_at(snapshot.at)
    correlated, pairs_seen, sources_seen, _ = _replay_correlations(snapshot, config=config)
    narratives = _replay_narratives(correlated, at=at)
    generated_at = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    correlated_dicts = tuple(sig.to_dict() for sig in correlated)
    narrative_dicts = tuple(thesis.to_dict() for thesis in narratives)
    envelope = {
        "generator": GENERATOR,
        "version": VERSION,
        "snapshot_at": snapshot.at,
        "snapshot_index_signature": snapshot.index_signature,
        "scope": list(snapshot.scope),
        "pairs_replayed": len(pairs_seen),
        "narratives_replayed": len(narrative_dicts),
        "sources_seen": sources_seen,
        "generated_at": generated_at,
        "warning": (
            "Replay output is research-only. It does not represent "
            "live state, has not been published to the event bus, "
            "and must not be used to place trades."
        ),
    }
    return ReplayResult(
        at=snapshot.at,
        correlated_signals=correlated_dicts,
        narratives=narrative_dicts,
        pairs_seen=tuple(pairs_seen),
        sources_seen=tuple(sources_seen),
        generated_at=generated_at,
        snapshot_index_signature=snapshot.index_signature,
        provenance_envelope=envelope,
    )


__all__ = [
    "GENERATOR",
    "VERSION",
    "ReplayResult",
    "replay",
]
