"""Per-source signal-to-noise measurement.

For every signal a source has emitted in the historical window we
attempt to match it to an *eventual outcome* (a directional realised
move that becomes available after the signal's lookahead window
elapses). The match yields one of four labels:

- ``true_positive``  — source said BULL/BEAR and outcome agreed
- ``false_positive`` — source said BULL/BEAR but outcome disagreed
- ``true_negative``  — source said NEUTRAL and outcome was indeed flat
- ``false_negative`` — source said NEUTRAL but outcome was strongly
  directional (we missed alpha)

Aggregating these across the window gives the per-source
:class:`SourceSNR` with precision, recall, and F1.

Design notes
------------
- ``score_signal_against_outcome`` is a *pure* function operating on a
  ``(SignalRecord, Outcome)`` pair. The caller is responsible for the
  matching join. We accept an explicit ``window_hours`` so a callsite
  with non-default lookahead (e.g., 24h Kronos, 4h Telegram) can pass
  its own value.
- F1 uses the standard harmonic mean of precision and recall, with the
  positive class being "non-NEUTRAL signal that agreed with outcome".
  When the source emitted no positive signals, precision is set to
  ``0.0`` rather than ``NaN`` to keep the JSON serialisable.
- The minimum-sample-size guard is conservative (5 signals): below
  that we still emit the dataclass but mark ``low_sample=True`` so the
  consumer (dashboard / plugin tool) can render it as low-confidence.

This module is read-only and free of network calls. The daemon at
``services/source_quality/run.py`` is the only thing that touches the
filesystem.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# A signal is "directional" if its absolute confidence-weighted intent
# crosses this floor. Anything below counts as NEUTRAL for the purposes
# of precision / recall accounting.
NEUTRAL_BAND = 0.10

# Lookahead default: 24h. Override per source if you have evidence the
# source's edge concentrates on a different horizon.
DEFAULT_OUTCOME_WINDOW_HOURS = 24

# Below this signal count, we still emit a SourceSNR but flag it.
MIN_SAMPLES_FOR_HIGH_CONFIDENCE = 5


@dataclass(frozen=True)
class SignalRecord:
    """One source emission, normalised to a stable schema."""

    source: str
    symbol: str
    timestamp: datetime
    direction: str  # "bull" | "bear" | "neutral"
    confidence: float = 1.0

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "symbol": self.symbol,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "direction": self.direction,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Outcome:
    """Eventual realised outcome for a ``(symbol, time)`` pair."""

    symbol: str
    timestamp: datetime
    realised_return: float  # signed; positive = up

    @property
    def direction(self) -> str:
        if self.realised_return > NEUTRAL_BAND:
            return "bull"
        if self.realised_return < -NEUTRAL_BAND:
            return "bear"
        return "neutral"


@dataclass(frozen=True)
class _Counts:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0


@dataclass(frozen=True)
class SourceSNR:
    """Aggregate quality metrics for a single source over a window."""

    source: str
    samples: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    window_start: str
    window_end: str
    low_sample: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "samples": self.samples,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
            "window_start": self.window_start,
            "window_end": self.window_end,
            "low_sample": self.low_sample,
            "notes": list(self.notes),
        }


def _classify_directional(value: str) -> str:
    """Normalise direction strings to one of bull/bear/neutral."""
    raw = (value or "").strip().lower()
    if raw in {"bull", "long", "buy", "+1"}:
        return "bull"
    if raw in {"bear", "short", "sell", "-1"}:
        return "bear"
    return "neutral"


def score_signal_against_outcome(
    signal: SignalRecord,
    outcome: Outcome,
) -> str:
    """Return one of {true_positive, false_positive, true_negative, false_negative}.

    The signal's effective direction is its declared direction unless
    confidence is below :data:`NEUTRAL_BAND`, in which case it falls
    back to neutral. The outcome's direction is derived from
    :attr:`Outcome.direction` (already band-aware).
    """
    if signal.symbol != outcome.symbol:
        msg = f"symbol mismatch: signal={signal.symbol!r} outcome={outcome.symbol!r}"
        raise ValueError(msg)
    sig_dir = _classify_directional(signal.direction)
    if sig_dir != "neutral" and abs(signal.confidence) < NEUTRAL_BAND:
        sig_dir = "neutral"
    out_dir = outcome.direction
    if sig_dir == "neutral" and out_dir == "neutral":
        return "true_negative"
    if sig_dir == "neutral" and out_dir != "neutral":
        return "false_negative"
    if sig_dir != "neutral" and out_dir == "neutral":
        return "false_positive"
    # both non-neutral
    if sig_dir == out_dir:
        return "true_positive"
    return "false_positive"


def _match_outcome(
    signal: SignalRecord,
    outcomes: list[Outcome],
    window_hours: int,
) -> Outcome | None:
    """Find the closest outcome within ``window_hours`` after the signal."""
    horizon = signal.timestamp + timedelta(hours=window_hours)
    best: Outcome | None = None
    best_delta = None
    for outcome in outcomes:
        if outcome.symbol != signal.symbol:
            continue
        if outcome.timestamp <= signal.timestamp:
            continue
        if outcome.timestamp > horizon:
            continue
        delta = (outcome.timestamp - signal.timestamp).total_seconds()
        if best is None or delta < best_delta:  # type: ignore[operator]
            best = outcome
            best_delta = delta
    return best


def compute_source_snr(
    signals: Iterable[SignalRecord],
    outcomes: Iterable[Outcome],
    *,
    window_hours: int = DEFAULT_OUTCOME_WINDOW_HOURS,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    snapshot_at: datetime | None = None,
) -> dict[str, SourceSNR]:
    """Compute per-source SNR over the joined signal+outcome stream.

    Parameters
    ----------
    signals
        Iterable of :class:`SignalRecord`. Order does not matter.
    outcomes
        Iterable of :class:`Outcome`. We match each signal to the
        earliest outcome inside its lookahead window.
    window_hours
        Lookahead horizon for the signal→outcome match.
    window_start, window_end
        Optional explicit reporting window — used as the
        ``window_start`` / ``window_end`` fields on the emitted
        :class:`SourceSNR`. If omitted we infer them from the data.
    snapshot_at
        **Lane 9 wiring (Lane 3 ↔ Lane 4)**. When provided, every
        signal whose ``timestamp > snapshot_at`` is dropped, and every
        outcome whose ``timestamp > snapshot_at`` is dropped. This
        gives the caller a deterministic "what was the SNR-as-of-T"
        view that is bit-identical to the SNR computed today over the
        same in-memory data, modulo the time-travel exclusion. When
        ``None`` (default) the function behaves exactly as before.

        Implementation note: this is purely a pre-filter. We do not
        load a time-travel snapshot from disk here — the caller is
        responsible for providing the data they want scored. The
        ``services.source_quality.run`` daemon and the time-travel
        plugin tool collaborate when an end-to-end snapshot SNR is
        needed; this kwarg exists so they can share one code path.

    Returns
    -------
    dict[str, SourceSNR]
        One entry per source. Empty dict if ``signals`` is empty.
    """
    sigs = list(signals)
    outs = list(outcomes)
    if snapshot_at is not None:
        # Tag-naive datetimes as UTC (consistent with the rest of the module).
        if snapshot_at.tzinfo is None:
            snapshot_at = snapshot_at.replace(tzinfo=UTC)
        sigs = [s for s in sigs if s.timestamp <= snapshot_at]
        outs = [o for o in outs if o.timestamp <= snapshot_at]
    if not sigs:
        return {}
    by_source: dict[str, list[SignalRecord]] = {}
    for s in sigs:
        by_source.setdefault(s.source, []).append(s)
    inferred_start = min(s.timestamp for s in sigs)
    inferred_end = max(s.timestamp for s in sigs)
    ws = (window_start or inferred_start).astimezone(UTC).isoformat()
    we = (window_end or inferred_end).astimezone(UTC).isoformat()
    out: dict[str, SourceSNR] = {}
    for source, source_sigs in sorted(by_source.items()):
        tp = fp = tn = fn = 0
        notes: list[str] = []
        unmatched = 0
        for sig in source_sigs:
            outcome = _match_outcome(sig, outs, window_hours)
            if outcome is None:
                unmatched += 1
                continue
            label = score_signal_against_outcome(sig, outcome)
            if label == "true_positive":
                tp += 1
            elif label == "false_positive":
                fp += 1
            elif label == "true_negative":
                tn += 1
            else:
                fn += 1
        counts = _Counts(tp=tp, fp=fp, tn=tn, fn=fn)
        if unmatched:
            notes.append(f"{unmatched} signal(s) had no outcome inside the {window_hours}h window")
        low_sample = counts.total < MIN_SAMPLES_FOR_HIGH_CONFIDENCE
        if low_sample and counts.total > 0:
            notes.append(
                f"sample size {counts.total} < {MIN_SAMPLES_FOR_HIGH_CONFIDENCE}; treat as preliminary"
            )
        out[source] = SourceSNR(
            source=source,
            samples=counts.total,
            true_positives=counts.tp,
            false_positives=counts.fp,
            true_negatives=counts.tn,
            false_negatives=counts.fn,
            precision=counts.precision,
            recall=counts.recall,
            f1=counts.f1,
            window_start=ws,
            window_end=we,
            low_sample=low_sample,
            notes=tuple(notes),
        )
    return out


__all__ = [
    "DEFAULT_OUTCOME_WINDOW_HOURS",
    "MIN_SAMPLES_FOR_HIGH_CONFIDENCE",
    "NEUTRAL_BAND",
    "Outcome",
    "SignalRecord",
    "SourceSNR",
    "compute_source_snr",
    "score_signal_against_outcome",
]
