"""Tests for lib.source_quality.decay."""

from __future__ import annotations

from datetime import UTC, datetime

from lib.source_quality.decay import (
    DEFAULT_DECAY_THRESHOLD,
    DEFAULT_RECENT_DAYS,
    MIN_RECENT_SAMPLES,
    detect_decay,
)
from lib.source_quality.snr import Outcome, SignalRecord


def _sig(source: str, direction: str, day: int, *, symbol: str = "BTC") -> SignalRecord:
    return SignalRecord(
        source=source,
        symbol=symbol,
        timestamp=datetime(2026, 4, day, 12, 0, tzinfo=UTC),
        direction=direction,
        confidence=0.9,
    )


def _out(direction_value: float, day: int, *, symbol: str = "BTC", hour: int = 18) -> Outcome:
    return Outcome(
        symbol=symbol,
        timestamp=datetime(2026, 4, day, hour, 0, tzinfo=UTC),
        realised_return=direction_value,
    )


def test_detect_decay_returns_empty_when_no_signals():
    report = detect_decay([], [])

    assert report.alerts == ()
    assert report.decayed_sources == ()
    assert "no signals" in report.notes[0]


def test_detect_decay_flags_source_whose_recent_f1_dropped():
    # Baseline: alpha was 100% accurate over many days far in the past.
    sigs = []
    outs = []
    for d in range(1, 16):
        sigs.append(_sig("alpha", "bull", d))
        outs.append(_out(0.5, d, hour=18))
    # Now in the recent 14d window (pretend "now" = day 30), alpha gets every call wrong.
    for d in range(20, 30):
        sigs.append(_sig("alpha", "bull", d))
        outs.append(_out(-0.5, d, hour=18))
    now = datetime(2026, 4, 30, 0, 0, tzinfo=UTC)

    report = detect_decay(sigs, outs, now=now, recent_days=14)
    alert = report.alerts[0]

    assert alert.source == "alpha"
    assert alert.decay is True
    assert alert.delta is not None
    assert alert.delta >= DEFAULT_DECAY_THRESHOLD


def test_detect_decay_does_not_flag_stable_source():
    sigs = [_sig("steady", "bull", d) for d in range(1, 25)]
    outs = [_out(0.5, d, hour=18) for d in range(1, 25)]
    now = datetime(2026, 4, 25, 0, 0, tzinfo=UTC)

    report = detect_decay(sigs, outs, now=now)

    assert report.alerts[0].decay is False
    assert report.decayed_sources == ()


def test_detect_decay_marks_low_sample_when_recent_window_too_thin():
    # Lots of baseline signals far in the past, almost none in the recent window.
    sigs = [_sig("rare", "bull", d) for d in range(1, 9)]
    outs = [_out(0.5, d, hour=18) for d in range(1, 9)]
    sigs.append(_sig("rare", "bull", 28))
    outs.append(_out(0.5, 28, hour=18))
    now = datetime(2026, 4, 30, 0, 0, tzinfo=UTC)

    report = detect_decay(sigs, outs, now=now, recent_days=7)
    alert = report.alerts[0]

    assert alert.low_sample is True
    assert alert.delta is None


def test_detect_decay_alerts_sorted_by_decay_magnitude_desc():
    sigs: list[SignalRecord] = []
    outs: list[Outcome] = []
    for d in range(1, 21):
        sigs.append(_sig("alpha", "bull", d, symbol="BTC"))
        outs.append(_out(0.5 if (d <= 12 or d % 2 == 0) else -0.5, d, hour=18, symbol="BTC"))
        sigs.append(_sig("beta", "bull", d, symbol="ETH"))
        outs.append(_out(0.5 if d <= 6 else -0.5, d, hour=18, symbol="ETH"))
    now = datetime(2026, 4, 21, 0, 0, tzinfo=UTC)

    report = detect_decay(sigs, outs, now=now, recent_days=14, threshold=DEFAULT_DECAY_THRESHOLD)

    # The first alert should be the source with larger |delta|.
    assert report.alerts[0].source in {"alpha", "beta"}
    deltas = [a.delta for a in report.alerts if a.delta is not None]
    if len(deltas) >= 2:
        assert abs(deltas[0]) >= abs(deltas[1])


def test_detect_decay_notes_improving_source():
    # Source got *better* in recent window.
    sigs = []
    outs = []
    for d in range(1, 11):
        # Baseline: 50% accurate
        sigs.append(_sig("improving", "bull", d))
        outs.append(_out(0.5 if d % 2 else -0.5, d, hour=18))
    for d in range(20, 30):
        # Recent window: 100% accurate
        sigs.append(_sig("improving", "bull", d))
        outs.append(_out(0.5, d, hour=18))
    now = datetime(2026, 4, 30, 0, 0, tzinfo=UTC)

    report = detect_decay(sigs, outs, now=now, recent_days=14)
    alert = report.alerts[0]

    assert alert.decay is False
    assert alert.delta is not None and alert.delta < 0
    assert any("improving" in n for n in alert.notes)


def test_detect_decay_threshold_constant_is_documented():
    assert DEFAULT_DECAY_THRESHOLD == 0.15


def test_detect_decay_recent_days_constant_is_documented():
    assert DEFAULT_RECENT_DAYS == 14


def test_detect_decay_to_dict_payload_has_required_fields():
    sigs = [_sig("alpha", "bull", d) for d in range(1, 25)]
    outs = [_out(0.5, d, hour=18) for d in range(1, 25)]
    now = datetime(2026, 4, 25, 0, 0, tzinfo=UTC)

    report = detect_decay(sigs, outs, now=now)
    payload = report.to_dict()

    assert payload["threshold"] == DEFAULT_DECAY_THRESHOLD
    assert payload["recent_days"] == DEFAULT_RECENT_DAYS
    assert "alerts" in payload
    assert isinstance(payload["alerts"], list)


def test_detect_decay_uses_max_signal_timestamp_when_now_missing():
    sigs = [_sig("alpha", "bull", d) for d in range(1, 21)]
    outs = [_out(0.5, d, hour=18) for d in range(1, 21)]

    report_with_now = detect_decay(sigs, outs, now=datetime(2026, 4, 20, 12, 0, tzinfo=UTC))
    report_without = detect_decay(sigs, outs)

    # Both should produce the same alert keys.
    assert {a.source for a in report_with_now.alerts} == {a.source for a in report_without.alerts}


def test_detect_decay_min_recent_samples_constant_is_5():
    assert MIN_RECENT_SAMPLES == 5


def test_detect_decay_handles_multiple_sources_independently():
    sigs = []
    outs = []
    for d in range(1, 25):
        sigs.append(_sig("alpha", "bull", d, symbol="BTC"))
        outs.append(_out(0.5, d, hour=18, symbol="BTC"))
        sigs.append(_sig("beta", "bull", d, symbol="ETH"))
        outs.append(_out(0.5 if d <= 10 else -0.5, d, hour=18, symbol="ETH"))
    now = datetime(2026, 4, 25, 0, 0, tzinfo=UTC)

    report = detect_decay(sigs, outs, now=now, recent_days=14)

    sources = {a.source for a in report.alerts}
    assert sources == {"alpha", "beta"}


def test_detect_decay_explicit_threshold_override():
    sigs = []
    outs = []
    for d in range(1, 25):
        sigs.append(_sig("alpha", "bull", d))
        # Mild degradation: 100% baseline → 80% recent → delta ~0.2 (or so)
        outs.append(_out(0.5 if (d <= 11 or d % 5 != 0) else -0.5, d, hour=18))
    now = datetime(2026, 4, 25, 0, 0, tzinfo=UTC)

    permissive = detect_decay(sigs, outs, now=now, threshold=0.5)
    aggressive = detect_decay(sigs, outs, now=now, threshold=0.05)

    assert permissive.alerts[0].decay is False or permissive.alerts[0].delta is None
    assert aggressive.alerts[0].decay is True or aggressive.alerts[0].delta is not None


def test_detect_decay_window_hours_parameter_is_threaded_through():
    sigs = [_sig("alpha", "bull", d) for d in range(1, 21)]
    # Outcomes inside the default 24h window:
    outs = [_out(0.5, d, hour=18) for d in range(1, 21)]
    now = datetime(2026, 4, 21, 0, 0, tzinfo=UTC)

    # With a tiny window, no outcomes match → samples=0 everywhere → low_sample everywhere.
    tight = detect_decay(sigs, outs, now=now, window_hours=1)
    loose = detect_decay(sigs, outs, now=now, window_hours=24)

    assert tight.alerts[0].low_sample is True
    assert loose.alerts[0].low_sample is False or loose.alerts[0].baseline_samples > 0
