"""Tests for lib.source_quality.snr."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lib.source_quality.snr import (
    DEFAULT_OUTCOME_WINDOW_HOURS,
    MIN_SAMPLES_FOR_HIGH_CONFIDENCE,
    NEUTRAL_BAND,
    Outcome,
    SignalRecord,
    SourceSNR,
    compute_source_snr,
    score_signal_against_outcome,
)


def _ts(day: int = 1, hour: int = 12) -> datetime:
    return datetime(2026, 4, day, hour, 0, tzinfo=UTC)


def _sig(
    source: str, direction: str, day: int = 1, *, conf: float = 0.8, symbol: str = "BTC"
) -> SignalRecord:
    return SignalRecord(
        source=source, symbol=symbol, timestamp=_ts(day, 12), direction=direction, confidence=conf
    )


def _out(direction_value: float, day: int = 1, *, hour: int = 18, symbol: str = "BTC") -> Outcome:
    return Outcome(symbol=symbol, timestamp=_ts(day, hour), realised_return=direction_value)


# ─── score_signal_against_outcome ────────────────────────────────────────


def test_score_true_positive_when_bull_signal_meets_bull_outcome():
    label = score_signal_against_outcome(_sig("tv", "bull"), _out(0.5))

    assert label == "true_positive"


def test_score_true_positive_when_bear_signal_meets_bear_outcome():
    label = score_signal_against_outcome(_sig("tv", "bear"), _out(-0.5))

    assert label == "true_positive"


def test_score_false_positive_when_bull_signal_meets_bear_outcome():
    label = score_signal_against_outcome(_sig("tv", "bull"), _out(-0.5))

    assert label == "false_positive"


def test_score_false_positive_when_bull_signal_meets_neutral_outcome():
    label = score_signal_against_outcome(_sig("tv", "bull"), _out(0.0))

    assert label == "false_positive"


def test_score_true_negative_when_neutral_signal_meets_neutral_outcome():
    label = score_signal_against_outcome(_sig("tv", "neutral"), _out(0.0))

    assert label == "true_negative"


def test_score_false_negative_when_neutral_signal_meets_bull_outcome():
    label = score_signal_against_outcome(_sig("tv", "neutral"), _out(0.5))

    assert label == "false_negative"


def test_score_low_confidence_demotes_to_neutral_classification():
    weak = _sig("tv", "bull", conf=NEUTRAL_BAND / 2)
    label = score_signal_against_outcome(weak, _out(0.0))

    assert label == "true_negative"


def test_score_raises_when_symbols_disagree():
    bad_sig = _sig("tv", "bull", symbol="ETH")
    with pytest.raises(ValueError):
        score_signal_against_outcome(bad_sig, _out(0.5, symbol="BTC"))


def test_score_classifies_synonym_buy_as_bull():
    label = score_signal_against_outcome(_sig("tv", "buy"), _out(0.5))

    assert label == "true_positive"


def test_score_classifies_synonym_sell_as_bear():
    label = score_signal_against_outcome(_sig("tv", "sell"), _out(-0.5))

    assert label == "true_positive"


# ─── compute_source_snr ───────────────────────────────────────────────────


def test_compute_snr_emits_one_entry_per_source():
    sigs = [_sig("alpha", "bull", day=1), _sig("beta", "bear", day=2)]
    outs = [_out(0.5, day=1, hour=18), _out(-0.5, day=2, hour=18)]

    result = compute_source_snr(sigs, outs)

    assert set(result.keys()) == {"alpha", "beta"}


def test_compute_snr_perfect_source_has_f1_one():
    sigs = [_sig("alpha", "bull", day=d) for d in range(1, 7)] + [
        _sig("alpha", "bear", day=d) for d in range(7, 13)
    ]
    outs = [_out(0.5, day=d, hour=18) for d in range(1, 7)] + [
        _out(-0.5, day=d, hour=18) for d in range(7, 13)
    ]

    snr = compute_source_snr(sigs, outs)["alpha"]

    assert snr.f1 == pytest.approx(1.0)
    assert snr.precision == pytest.approx(1.0)
    assert snr.recall == pytest.approx(1.0)
    assert snr.low_sample is False


def test_compute_snr_marks_low_sample_below_threshold():
    sigs = [_sig("alpha", "bull", day=1)]
    outs = [_out(0.5, day=1, hour=18)]

    snr = compute_source_snr(sigs, outs)["alpha"]

    assert snr.low_sample is True
    assert snr.samples == 1
    assert any("preliminary" in n for n in snr.notes)


def test_compute_snr_returns_empty_dict_when_no_signals():
    result = compute_source_snr([], [])

    assert result == {}


def test_compute_snr_skips_signals_with_no_outcome_in_window():
    sig = _sig("alpha", "bull", day=1)
    far_outcome = Outcome(symbol="BTC", timestamp=_ts(15, 0), realised_return=0.5)

    result = compute_source_snr([sig], [far_outcome], window_hours=DEFAULT_OUTCOME_WINDOW_HOURS)

    snr = result["alpha"]
    assert snr.samples == 0
    assert any("no outcome" in n for n in snr.notes)


def test_compute_snr_window_start_end_use_provided_overrides():
    sigs = [_sig("alpha", "bull", day=2)]
    outs = [_out(0.5, day=2, hour=18)]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 12, 31, tzinfo=UTC)

    snr = compute_source_snr(sigs, outs, window_start=start, window_end=end)["alpha"]

    assert snr.window_start == start.isoformat()
    assert snr.window_end == end.isoformat()


def test_compute_snr_to_dict_is_json_safe():
    sigs = [_sig("alpha", "bull", day=d) for d in range(1, 7)]
    outs = [_out(0.5, day=d, hour=18) for d in range(1, 7)]

    snr = compute_source_snr(sigs, outs)["alpha"]
    payload = snr.to_dict()

    import json as _json

    serialised = _json.dumps(payload, sort_keys=True)
    assert "alpha" in serialised
    assert payload["precision"] <= 1.0


def test_compute_snr_partial_accuracy_yields_intermediate_f1():
    # 6 bull signals: 4 with bull outcome, 2 with bear outcome.
    sigs = [_sig("alpha", "bull", day=d) for d in range(1, 7)]
    outs = [
        _out(0.5, day=1, hour=18),
        _out(0.5, day=2, hour=18),
        _out(0.5, day=3, hour=18),
        _out(0.5, day=4, hour=18),
        _out(-0.5, day=5, hour=18),
        _out(-0.5, day=6, hour=18),
    ]

    snr = compute_source_snr(sigs, outs)["alpha"]

    assert 0 < snr.precision < 1
    assert snr.true_positives == 4
    assert snr.false_positives == 2


def test_compute_snr_separates_per_source_independently():
    sigs = [
        _sig("alpha", "bull", day=1),
        _sig("alpha", "bull", day=2),
        _sig("alpha", "bull", day=3),
        _sig("alpha", "bull", day=4),
        _sig("alpha", "bull", day=5),
        _sig("beta", "bear", day=1),
        _sig("beta", "bear", day=2),
        _sig("beta", "bear", day=3),
        _sig("beta", "bear", day=4),
        _sig("beta", "bear", day=5),
    ]
    outs = [_out(0.5, day=d, hour=18) for d in range(1, 6)] + [
        _out(0.5, day=d, hour=18)
        for d in range(1, 6)  # alpha right, beta wrong
    ]

    res = compute_source_snr(sigs, outs)

    # Each source only sees its own outcomes; alpha had all hits, beta all misses.
    assert res["alpha"].precision == pytest.approx(1.0)
    assert res["beta"].precision == pytest.approx(0.0)


def test_compute_snr_default_window_hours_constant_is_24():
    assert DEFAULT_OUTCOME_WINDOW_HOURS == 24


def test_compute_snr_min_sample_constant_is_5():
    assert MIN_SAMPLES_FOR_HIGH_CONFIDENCE == 5


def test_signal_record_as_dict_round_trip():
    sig = _sig("alpha", "bull", day=1)

    payload = sig.as_dict()

    assert payload["source"] == "alpha"
    assert payload["direction"] == "bull"
    assert payload["timestamp"].endswith("+00:00")


def test_outcome_direction_respects_neutral_band():
    # below band → neutral
    assert (
        Outcome(symbol="BTC", timestamp=_ts(1), realised_return=NEUTRAL_BAND / 2).direction
        == "neutral"
    )
    assert (
        Outcome(symbol="BTC", timestamp=_ts(1), realised_return=NEUTRAL_BAND * 2).direction
        == "bull"
    )
    assert (
        Outcome(symbol="BTC", timestamp=_ts(1), realised_return=-NEUTRAL_BAND * 2).direction
        == "bear"
    )


def test_compute_snr_matches_first_outcome_inside_window():
    sig = _sig("alpha", "bull", day=1)
    out_in_window = Outcome(symbol="BTC", timestamp=_ts(1, 14), realised_return=0.5)
    out_later = Outcome(symbol="BTC", timestamp=_ts(1, 18), realised_return=-0.5)

    res = compute_source_snr([sig], [out_in_window, out_later])

    assert res["alpha"].true_positives == 1


def test_source_snr_dataclass_round_trip_via_from_dict_unsupported_explicit():
    sigs = [_sig("alpha", "bull", day=d) for d in range(1, 7)]
    outs = [_out(0.5, day=d, hour=18) for d in range(1, 7)]

    snr_obj = compute_source_snr(sigs, outs)["alpha"]

    assert isinstance(snr_obj, SourceSNR)
    assert (
        snr_obj.true_positives
        + snr_obj.false_positives
        + snr_obj.true_negatives
        + snr_obj.false_negatives
        == snr_obj.samples
    )


def test_compute_snr_handles_identical_timestamps_for_different_symbols():
    sig_btc = SignalRecord(
        source="alpha", symbol="BTC", timestamp=_ts(1), direction="bull", confidence=0.9
    )
    sig_eth = SignalRecord(
        source="alpha", symbol="ETH", timestamp=_ts(1), direction="bull", confidence=0.9
    )
    out_btc = Outcome(symbol="BTC", timestamp=_ts(1) + timedelta(hours=1), realised_return=0.5)
    out_eth = Outcome(symbol="ETH", timestamp=_ts(1) + timedelta(hours=1), realised_return=-0.5)

    res = compute_source_snr([sig_btc, sig_eth], [out_btc, out_eth])

    assert res["alpha"].samples == 2
    # BTC right, ETH wrong → 1 TP + 1 FP
    assert res["alpha"].true_positives == 1
    assert res["alpha"].false_positives == 1
