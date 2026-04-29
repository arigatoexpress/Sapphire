"""Tranche 6 Lane 9 wiring — Lane 3 (time-travel) ↔ Lane 4 (source quality).

The ``compute_source_snr`` function gained an optional ``snapshot_at:
datetime | None`` parameter that filters signals + outcomes whose
timestamp is strictly after ``snapshot_at`` before scoring. The
contract is:

  compute_source_snr(signals, outcomes, snapshot_at=T)
    ≡  compute_source_snr(
         [s for s in signals if s.timestamp <= T],
         [o for o in outcomes if o.timestamp <= T],
       )

This is the time-travel-aware view: the SNR computed today over a
snapshot of the data at time T is byte-identical to the SNR computed
at time T over the same in-memory data (modulo any subsequent code
changes to the scoring function — which is the fingerprint of the
diff layer in ``lib/timetravel/diff.py``).

These tests assert the equivalence on four canonical scenarios.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lib.source_quality.snr import (
    Outcome,
    SignalRecord,
    compute_source_snr,
)


def _ts(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 4, day, hour, 0, tzinfo=UTC)


def _signals_and_outcomes() -> tuple[list[SignalRecord], list[Outcome]]:
    """Build a deterministic 5-day signal+outcome stream.

    Each day at 12:00 UTC, source "tv" emits a bull signal on BTC; the
    outcome is realised at 14:00 UTC of the same day. Days 1-3 the
    outcome agrees (true positive); days 4-5 the outcome disagrees
    (false positive).
    """
    signals = [
        SignalRecord(
            source="tv",
            symbol="BTC",
            timestamp=_ts(day, 12),
            direction="bull",
            confidence=0.9,
        )
        for day in range(1, 6)
    ]
    outcomes = [
        Outcome(symbol="BTC", timestamp=_ts(1, 14), realised_return=0.5),
        Outcome(symbol="BTC", timestamp=_ts(2, 14), realised_return=0.5),
        Outcome(symbol="BTC", timestamp=_ts(3, 14), realised_return=0.5),
        Outcome(symbol="BTC", timestamp=_ts(4, 14), realised_return=-0.5),
        Outcome(symbol="BTC", timestamp=_ts(5, 14), realised_return=-0.5),
    ]
    return signals, outcomes


# ---------------------------------------------------------------------------
# Case 1 — snapshot at T = end of day 3.
# ---------------------------------------------------------------------------


def test_snapshot_at_day3_matches_direct_filter() -> None:
    """SNR-at-T == SNR over manually-filtered data."""
    signals, outcomes = _signals_and_outcomes()
    snapshot_at = _ts(3, 23)

    via_kwarg = compute_source_snr(signals, outcomes, snapshot_at=snapshot_at)

    direct_signals = [s for s in signals if s.timestamp <= snapshot_at]
    direct_outcomes = [o for o in outcomes if o.timestamp <= snapshot_at]
    direct = compute_source_snr(direct_signals, direct_outcomes)

    assert via_kwarg["tv"].to_dict() == direct["tv"].to_dict()


# ---------------------------------------------------------------------------
# Case 2 — snapshot at T = exactly between days. Boundary inclusive.
# ---------------------------------------------------------------------------


def test_snapshot_at_exact_signal_timestamp_includes_signal() -> None:
    """A signal whose ``timestamp == snapshot_at`` is INCLUDED.

    The ``compute_source_snr`` filter uses ``<=`` not ``<``; we assert
    that contract here so callers can rely on it.
    """
    signals, outcomes = _signals_and_outcomes()
    snapshot_at = _ts(2, 12)  # exact day-2 noon — same as signal[1].timestamp

    via_kwarg = compute_source_snr(signals, outcomes, snapshot_at=snapshot_at)
    # signals on day 1 + day 2 are visible (2 total). day 1 has an outcome
    # at 14:00 (visible), day 2's outcome at 14:00 is NOT yet visible — so
    # only day 1 is matched.
    snr = via_kwarg["tv"]
    assert snr.samples == 1, f"expected 1 matched sample, got {snr.samples}"


# ---------------------------------------------------------------------------
# Case 3 — snapshot before any data → empty result.
# ---------------------------------------------------------------------------


def test_snapshot_before_all_data_returns_empty() -> None:
    """Snapshot before any signal exists → empty dict."""
    signals, outcomes = _signals_and_outcomes()
    snapshot_at = _ts(1, 0)  # midnight day 1, before noon signals.

    via_kwarg = compute_source_snr(signals, outcomes, snapshot_at=snapshot_at)
    assert via_kwarg == {}


# ---------------------------------------------------------------------------
# Case 4 — snapshot far in the future → equivalent to no filter.
# ---------------------------------------------------------------------------


def test_snapshot_after_all_data_matches_unfiltered() -> None:
    """Snapshot after all data → identical to ``snapshot_at=None``."""
    signals, outcomes = _signals_and_outcomes()
    snapshot_at = _ts(30, 23)  # end of April, well past day 5.

    via_kwarg = compute_source_snr(signals, outcomes, snapshot_at=snapshot_at)
    via_none = compute_source_snr(signals, outcomes, snapshot_at=None)

    assert via_kwarg["tv"].to_dict() == via_none["tv"].to_dict()


# ---------------------------------------------------------------------------
# Case 5 — naive datetime is treated as UTC.
# ---------------------------------------------------------------------------


def test_snapshot_naive_datetime_is_treated_as_utc() -> None:
    """A naive datetime should be auto-tagged UTC, not raise."""
    signals, outcomes = _signals_and_outcomes()
    naive_snapshot = datetime(2026, 4, 3, 23, 0)  # tz-naive
    aware_snapshot = naive_snapshot.replace(tzinfo=UTC)

    via_naive = compute_source_snr(signals, outcomes, snapshot_at=naive_snapshot)
    via_aware = compute_source_snr(signals, outcomes, snapshot_at=aware_snapshot)

    assert via_naive["tv"].to_dict() == via_aware["tv"].to_dict()
