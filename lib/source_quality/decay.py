"""Source decay detection.

A source is "decaying" when its rolling-window F1 has dropped
materially below its longer baseline F1. The default policy:

- ``baseline``  → F1 over the full historical window
- ``recent``    → F1 over the last ``recent_days`` (default 14)
- ``threshold`` → flag when ``recent < baseline - DEFAULT_DECAY_THRESHOLD``

Output is a :class:`DecayReport` with a per-source :class:`DecayAlert`
list. The list is sorted by absolute decay magnitude (worst first).

Notes
-----
- We compute baseline + recent F1 from the same :func:`compute_source_snr`
  primitive, just sliced over different windows. This keeps the decay
  module a thin orchestrator on top of :mod:`snr`.
- A source whose recent F1 is *better* than baseline is **not** flagged
  but is still emitted with ``decay=False`` and a positive ``delta``.
  Consumers may surface "improving sources" in a separate panel.
- We require ``MIN_RECENT_SAMPLES`` data points in the recent window
  before we'll emit a numeric delta. Otherwise the alert is marked
  ``low_sample=True`` and ``delta=None``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from lib.source_quality.snr import (
    DEFAULT_OUTCOME_WINDOW_HOURS,
    Outcome,
    SignalRecord,
    compute_source_snr,
)

# Flag if (baseline_f1 - recent_f1) >= this delta.
DEFAULT_DECAY_THRESHOLD = 0.15

# Default rolling window for "recent" F1.
DEFAULT_RECENT_DAYS = 14

# Below this many recent samples we won't emit a numeric delta.
MIN_RECENT_SAMPLES = 5


@dataclass(frozen=True)
class DecayAlert:
    """One per-source decay observation."""

    source: str
    baseline_f1: float
    recent_f1: float | None
    delta: float | None  # baseline - recent. Positive = decay.
    baseline_samples: int
    recent_samples: int
    decay: bool
    low_sample: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "baseline_f1": round(self.baseline_f1, 6),
            "recent_f1": (None if self.recent_f1 is None else round(self.recent_f1, 6)),
            "delta": (None if self.delta is None else round(self.delta, 6)),
            "baseline_samples": self.baseline_samples,
            "recent_samples": self.recent_samples,
            "decay": self.decay,
            "low_sample": self.low_sample,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class DecayReport:
    """Aggregate decay report over a stream of signals + outcomes."""

    alerts: tuple[DecayAlert, ...]
    decayed_sources: tuple[str, ...]
    threshold: float
    recent_days: int
    window_hours: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "recent_days": self.recent_days,
            "window_hours": self.window_hours,
            "alerts": [a.to_dict() for a in self.alerts],
            "decayed_sources": list(self.decayed_sources),
            "notes": list(self.notes),
        }


def _slice_recent(
    signals: Iterable[SignalRecord],
    *,
    now: datetime,
    recent_days: int,
) -> list[SignalRecord]:
    cutoff = now - timedelta(days=recent_days)
    return [s for s in signals if s.timestamp >= cutoff]


def _slice_outcomes_recent(
    outcomes: Iterable[Outcome],
    *,
    now: datetime,
    recent_days: int,
) -> list[Outcome]:
    cutoff = now - timedelta(days=recent_days)
    return [o for o in outcomes if o.timestamp >= cutoff]


def detect_decay(
    signals: Iterable[SignalRecord],
    outcomes: Iterable[Outcome],
    *,
    now: datetime | None = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
    threshold: float = DEFAULT_DECAY_THRESHOLD,
    window_hours: int = DEFAULT_OUTCOME_WINDOW_HOURS,
) -> DecayReport:
    """Compute baseline + recent F1 per source and flag decayed sources.

    Parameters
    ----------
    signals, outcomes
        Same shapes as :func:`compute_source_snr`.
    now
        Reference timestamp for the "recent" window. Defaults to the
        max signal timestamp (deterministic) so unit tests don't need
        clock control. If ``signals`` is empty we use ``datetime.now(UTC)``.
    recent_days
        Window width for the recent F1 computation.
    threshold
        Decay flag threshold on ``baseline_f1 - recent_f1``.
    window_hours
        Lookahead horizon passed through to :func:`compute_source_snr`.
    """
    sigs = list(signals)
    outs = list(outcomes)
    if not sigs:
        return DecayReport(
            alerts=(),
            decayed_sources=(),
            threshold=threshold,
            recent_days=recent_days,
            window_hours=window_hours,
            notes=("no signals supplied",),
        )
    reference = now or max(s.timestamp for s in sigs)
    baseline_snr = compute_source_snr(sigs, outs, window_hours=window_hours)
    recent_sigs = _slice_recent(sigs, now=reference, recent_days=recent_days)
    recent_outs = _slice_outcomes_recent(outs, now=reference, recent_days=recent_days)
    recent_snr = compute_source_snr(recent_sigs, recent_outs, window_hours=window_hours)
    alerts: list[DecayAlert] = []
    for source, baseline in sorted(baseline_snr.items()):
        recent = recent_snr.get(source)
        if recent is None or recent.samples < MIN_RECENT_SAMPLES:
            alerts.append(
                DecayAlert(
                    source=source,
                    baseline_f1=baseline.f1,
                    recent_f1=None if recent is None else recent.f1,
                    delta=None,
                    baseline_samples=baseline.samples,
                    recent_samples=0 if recent is None else recent.samples,
                    decay=False,
                    low_sample=True,
                    notes=(
                        "insufficient recent samples to compute decay",
                    ),
                )
            )
            continue
        delta = baseline.f1 - recent.f1
        decayed = delta >= threshold
        notes_t: tuple[str, ...] = ()
        if delta < 0:
            notes_t = ("recent F1 exceeds baseline — improving",)
        alerts.append(
            DecayAlert(
                source=source,
                baseline_f1=baseline.f1,
                recent_f1=recent.f1,
                delta=delta,
                baseline_samples=baseline.samples,
                recent_samples=recent.samples,
                decay=decayed,
                low_sample=False,
                notes=notes_t,
            )
        )
    alerts.sort(
        key=lambda a: (-(abs(a.delta) if a.delta is not None else -1.0), a.source)
    )
    decayed_sources = tuple(a.source for a in alerts if a.decay)
    return DecayReport(
        alerts=tuple(alerts),
        decayed_sources=decayed_sources,
        threshold=threshold,
        recent_days=recent_days,
        window_hours=window_hours,
        notes=(),
    )


# Re-export for convenience
__all__ = [
    "DEFAULT_DECAY_THRESHOLD",
    "DEFAULT_RECENT_DAYS",
    "DecayAlert",
    "DecayReport",
    "MIN_RECENT_SAMPLES",
    "detect_decay",
]


# Allow downstream to import _now helper
def _utc_now() -> datetime:
    return datetime.now(UTC)
