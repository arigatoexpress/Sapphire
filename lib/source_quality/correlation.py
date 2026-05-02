"""Pairwise cross-source correlation.

Two sources A and B agree on a ``(symbol, timestamp_bucket)`` cell when
both emitted a non-neutral signal in the same direction at roughly the
same time. The pairwise *agreement rate* is the share of overlapping
cells where they agreed.

We surface pairs whose agreement rate ≥ :data:`NEAR_DUPLICATE_THRESHOLD`
as candidate near-duplicates — operator should either downweight one or
verify they're not just both seeing the same prior (e.g., three Telegram
channels that all forward from the same OG).

Determinism
-----------
All inputs are dataclasses; the emitted :class:`CorrelationReport` has
its pair list sorted by ``(source_a, source_b)`` so equivalent input
yields identical bytes. Time bucketing snaps signals to the nearest
``bucket_minutes`` boundary; default 60 minutes.

Edge cases
----------
- A pair with fewer than ``min_overlap`` shared cells returns
  ``agreement_rate=None`` instead of a number — we don't extrapolate.
- A source that emitted only neutral signals contributes nothing to any
  pair.
- A perfectly anti-correlated pair (always opposite direction) has
  ``agreement_rate ≈ 0`` and is *not* flagged as near-duplicate. The
  consumer is welcome to inspect ``conflict_rate`` if they want.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from lib.source_quality.snr import SignalRecord, _classify_directional

# Pairs with agreement rate ≥ this threshold are flagged as near-duplicate.
NEAR_DUPLICATE_THRESHOLD = 0.87

# Below this overlap count we don't emit a numeric agreement rate.
DEFAULT_MIN_OVERLAP = 5

# Default time bucket for "same time" matching, in minutes.
DEFAULT_BUCKET_MINUTES = 60


def _bucket_key(ts: datetime, bucket_minutes: int) -> datetime:
    """Snap ``ts`` to the floor of its ``bucket_minutes`` boundary in UTC."""
    ts_utc = ts.astimezone(UTC)
    seconds = bucket_minutes * 60
    epoch = int(ts_utc.timestamp())
    floored = (epoch // seconds) * seconds
    return datetime.fromtimestamp(floored, tz=UTC)


@dataclass(frozen=True)
class CorrelationPair:
    """One pairwise correlation observation."""

    source_a: str
    source_b: str
    overlap: int
    agreements: int
    conflicts: int
    agreement_rate: float | None
    conflict_rate: float | None
    near_duplicate: bool

    def to_dict(self) -> dict:
        return {
            "source_a": self.source_a,
            "source_b": self.source_b,
            "overlap": self.overlap,
            "agreements": self.agreements,
            "conflicts": self.conflicts,
            "agreement_rate": (
                None if self.agreement_rate is None else round(self.agreement_rate, 6)
            ),
            "conflict_rate": (None if self.conflict_rate is None else round(self.conflict_rate, 6)),
            "near_duplicate": self.near_duplicate,
        }


@dataclass(frozen=True)
class CorrelationReport:
    """Full pairwise correlation report for a source universe."""

    pairs: tuple[CorrelationPair, ...]
    sources: tuple[str, ...]
    bucket_minutes: int
    min_overlap: int
    near_duplicate_threshold: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "sources": list(self.sources),
            "bucket_minutes": self.bucket_minutes,
            "min_overlap": self.min_overlap,
            "near_duplicate_threshold": self.near_duplicate_threshold,
            "pairs": [p.to_dict() for p in self.pairs],
            "near_duplicates": [p.to_dict() for p in self.pairs if p.near_duplicate],
            "notes": list(self.notes),
        }


def _signal_dir(s: SignalRecord) -> str:
    """Return the effective direction respecting the neutral band."""
    return _classify_directional(s.direction)


def _index_signals(
    signals: Iterable[SignalRecord],
    bucket_minutes: int,
) -> dict[str, dict[tuple[str, datetime], str]]:
    """Index signals by source → (symbol, time-bucket) → direction.

    When a single source emits multiple signals in the same bucket we
    keep the *latest* one — it represents the source's most recent
    intent for that period.
    """
    index: dict[str, dict[tuple[str, datetime], tuple[datetime, str]]] = {}
    for sig in signals:
        direction = _signal_dir(sig)
        if direction == "neutral":
            continue
        bucket = _bucket_key(sig.timestamp, bucket_minutes)
        per_source = index.setdefault(sig.source, {})
        cell = (sig.symbol, bucket)
        prev = per_source.get(cell)
        if prev is None or prev[0] < sig.timestamp:
            per_source[cell] = (sig.timestamp, direction)
    return {
        src: {cell: dir_ for cell, (_ts, dir_) in cells.items()} for src, cells in index.items()
    }


def compute_pairwise_correlation(
    signals: Iterable[SignalRecord],
    *,
    bucket_minutes: int = DEFAULT_BUCKET_MINUTES,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
    near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> CorrelationReport:
    """Compute pairwise correlation across all sources in the stream.

    Parameters
    ----------
    signals
        Iterable of :class:`SignalRecord`.
    bucket_minutes
        Time bucket width for "same time" matching.
    min_overlap
        Minimum shared cells before we emit a numeric agreement rate.
    near_duplicate_threshold
        Agreement rate ≥ this value flags the pair.
    """
    indexed = _index_signals(signals, bucket_minutes)
    sources = tuple(sorted(indexed.keys()))
    pairs: list[CorrelationPair] = []
    notes: list[str] = []
    if len(sources) < 2:
        notes.append("fewer than 2 sources have non-neutral signals; no pairs emitted")
        return CorrelationReport(
            pairs=(),
            sources=sources,
            bucket_minutes=bucket_minutes,
            min_overlap=min_overlap,
            near_duplicate_threshold=near_duplicate_threshold,
            notes=tuple(notes),
        )
    for i, a in enumerate(sources):
        for b in sources[i + 1 :]:
            cells_a = indexed[a]
            cells_b = indexed[b]
            common = set(cells_a) & set(cells_b)
            overlap = len(common)
            agreements = sum(1 for cell in common if cells_a[cell] == cells_b[cell])
            conflicts = overlap - agreements
            if overlap < min_overlap:
                rate: float | None = None
                conflict_rate: float | None = None
            else:
                rate = agreements / overlap
                conflict_rate = conflicts / overlap
            near_dup = bool(rate is not None and rate >= near_duplicate_threshold)
            pairs.append(
                CorrelationPair(
                    source_a=a,
                    source_b=b,
                    overlap=overlap,
                    agreements=agreements,
                    conflicts=conflicts,
                    agreement_rate=rate,
                    conflict_rate=conflict_rate,
                    near_duplicate=near_dup,
                )
            )
    pairs.sort(key=lambda p: (p.source_a, p.source_b))
    return CorrelationReport(
        pairs=tuple(pairs),
        sources=sources,
        bucket_minutes=bucket_minutes,
        min_overlap=min_overlap,
        near_duplicate_threshold=near_duplicate_threshold,
        notes=tuple(notes),
    )


def flag_near_duplicates(
    report: CorrelationReport,
    *,
    threshold: float | None = None,
) -> tuple[CorrelationPair, ...]:
    """Return all pairs whose agreement rate is at or above ``threshold``."""
    cutoff = threshold if threshold is not None else report.near_duplicate_threshold
    return tuple(
        p for p in report.pairs if p.agreement_rate is not None and p.agreement_rate >= cutoff
    )


def correlation_matrix(report: CorrelationReport) -> dict[str, dict[str, float | None]]:
    """Return a symmetric matrix of agreement rates keyed by source name.

    The diagonal is ``1.0`` for any source that appears in
    ``report.sources``; off-diagonal cells use the pair's
    ``agreement_rate`` (which may be ``None`` when overlap is below
    threshold).
    """
    matrix: dict[str, dict[str, float | None]] = {
        s: {t: (1.0 if s == t else None) for t in report.sources} for s in report.sources
    }
    for pair in report.pairs:
        matrix[pair.source_a][pair.source_b] = pair.agreement_rate
        matrix[pair.source_b][pair.source_a] = pair.agreement_rate
    return matrix


# Convenience constant import for downstream consumers
_DEFAULT_BUCKET = timedelta(minutes=DEFAULT_BUCKET_MINUTES)


__all__ = [
    "CorrelationPair",
    "CorrelationReport",
    "DEFAULT_BUCKET_MINUTES",
    "DEFAULT_MIN_OVERLAP",
    "NEAR_DUPLICATE_THRESHOLD",
    "compute_pairwise_correlation",
    "correlation_matrix",
    "flag_near_duplicates",
]
