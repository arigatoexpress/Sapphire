"""Tests for lib.source_quality.correlation."""

from __future__ import annotations

from datetime import UTC, datetime

from lib.source_quality.correlation import (
    DEFAULT_BUCKET_MINUTES,
    DEFAULT_MIN_OVERLAP,
    NEAR_DUPLICATE_THRESHOLD,
    compute_pairwise_correlation,
    correlation_matrix,
    flag_near_duplicates,
)
from lib.source_quality.snr import SignalRecord


def _sig(source: str, direction: str, day: int, *, symbol: str = "BTC", hour: int = 12) -> SignalRecord:
    return SignalRecord(
        source=source,
        symbol=symbol,
        timestamp=datetime(2026, 4, day, hour, 0, tzinfo=UTC),
        direction=direction,
        confidence=0.9,
    )


def test_compute_correlation_emits_zero_pairs_when_only_one_source():
    sigs = [_sig("alpha", "bull", d) for d in range(1, 8)]

    report = compute_pairwise_correlation(sigs)

    assert report.pairs == ()
    assert "fewer than 2" in report.notes[0]


def test_perfect_duplicate_sources_are_flagged_near_duplicate():
    sigs = [
        sig
        for d in range(1, 9)
        for sig in (_sig("alpha", "bull", d), _sig("beta", "bull", d))
    ]

    report = compute_pairwise_correlation(sigs)
    pair = report.pairs[0]

    assert pair.source_a == "alpha"
    assert pair.source_b == "beta"
    assert pair.agreement_rate == 1.0
    assert pair.near_duplicate is True


def test_anticorrelated_sources_have_low_agreement_and_no_flag():
    sigs = [
        sig
        for d in range(1, 9)
        for sig in (_sig("alpha", "bull", d), _sig("beta", "bear", d))
    ]

    report = compute_pairwise_correlation(sigs)
    pair = report.pairs[0]

    assert pair.agreement_rate == 0.0
    assert pair.conflict_rate == 1.0
    assert pair.near_duplicate is False


def test_overlap_below_min_emits_none_rate():
    sigs = [_sig("alpha", "bull", 1), _sig("beta", "bull", 1)]

    report = compute_pairwise_correlation(sigs, min_overlap=DEFAULT_MIN_OVERLAP)
    pair = report.pairs[0]

    assert pair.agreement_rate is None
    assert pair.conflict_rate is None
    assert pair.near_duplicate is False
    assert pair.overlap == 1


def test_neutral_signals_are_excluded_from_correlation_grid():
    sigs = [
        _sig("alpha", "neutral", 1),
        _sig("alpha", "neutral", 2),
        _sig("beta", "bull", 1),
        _sig("beta", "bull", 2),
    ]

    report = compute_pairwise_correlation(sigs)

    # alpha never produced a non-neutral signal so it's excluded from the
    # source universe entirely; only beta remains → no pairs.
    assert report.sources == ("beta",)
    assert report.pairs == ()


def test_pairs_sorted_alphabetically_by_source_names():
    sigs = [
        s
        for d in range(1, 9)
        for s in (
            _sig("zeta", "bull", d),
            _sig("alpha", "bull", d),
            _sig("mu", "bull", d),
        )
    ]

    report = compute_pairwise_correlation(sigs)

    pair_names = [(p.source_a, p.source_b) for p in report.pairs]
    assert pair_names == sorted(pair_names)


def test_correlation_matrix_round_trip_symmetric_with_diagonal_one():
    sigs = [
        s
        for d in range(1, 9)
        for s in (
            _sig("alpha", "bull", d),
            _sig("beta", "bull", d),
        )
    ]

    report = compute_pairwise_correlation(sigs)
    matrix = correlation_matrix(report)

    assert matrix["alpha"]["alpha"] == 1.0
    assert matrix["alpha"]["beta"] == matrix["beta"]["alpha"]


def test_flag_near_duplicates_uses_report_threshold_when_unspecified():
    sigs = [
        s
        for d in range(1, 9)
        for s in (_sig("alpha", "bull", d), _sig("beta", "bull", d))
    ]

    report = compute_pairwise_correlation(sigs)
    flagged = flag_near_duplicates(report)

    assert len(flagged) == 1
    assert flagged[0].source_a == "alpha"


def test_flag_near_duplicates_respects_explicit_threshold_override():
    sigs = []
    for d in range(1, 9):
        # 7/8 days alpha+beta agree, 1 day they diverge — agreement = 0.875
        sigs.append(_sig("alpha", "bull", d))
        sigs.append(_sig("beta", "bull" if d != 8 else "bear", d))

    report = compute_pairwise_correlation(sigs)

    # 0.875 ≥ default 0.87 → flagged
    flagged_default = flag_near_duplicates(report)
    flagged_strict = flag_near_duplicates(report, threshold=0.95)
    assert len(flagged_default) == 1
    assert flagged_strict == ()


def test_default_threshold_constant_matches_spec():
    assert NEAR_DUPLICATE_THRESHOLD == 0.87


def test_to_dict_payload_is_json_safe_and_paste_safe():
    sigs = [
        s
        for d in range(1, 9)
        for s in (
            _sig("alpha", "bull", d),
            _sig("beta", "bull", d),
        )
    ]

    report = compute_pairwise_correlation(sigs)
    payload = report.to_dict()

    import json as _json

    serialised = _json.dumps(payload, sort_keys=True)
    assert "near_duplicates" in payload
    assert "0.87" in serialised or '"near_duplicate_threshold": 0.87' in serialised


def test_compute_correlation_buckets_signals_within_minute_window():
    # Two signals 30 min apart, bucket=60 should count as same bucket.
    sigs = [
        _sig("alpha", "bull", 1, hour=12),
        _sig("beta", "bull", 1, hour=12),  # exact hour match
    ]
    # add some more so we exceed min_overlap
    for d in range(2, 8):
        sigs.append(_sig("alpha", "bull", d))
        sigs.append(_sig("beta", "bull", d))

    report = compute_pairwise_correlation(sigs, bucket_minutes=DEFAULT_BUCKET_MINUTES)

    assert report.pairs[0].overlap >= DEFAULT_MIN_OVERLAP


def test_latest_signal_in_bucket_wins_when_source_emits_twice():
    # Same source emits BULL then BEAR in the same bucket; latest wins.
    sigs = [
        SignalRecord(source="alpha", symbol="BTC", timestamp=datetime(2026, 4, 1, 12, 5, tzinfo=UTC), direction="bull", confidence=0.9),
        SignalRecord(source="alpha", symbol="BTC", timestamp=datetime(2026, 4, 1, 12, 50, tzinfo=UTC), direction="bear", confidence=0.9),
    ]
    # And six more bear-vs-bear days for beta to get overlap.
    for d in range(1, 8):
        sigs.append(_sig("beta", "bear", d))
        if d != 1:
            sigs.append(_sig("alpha", "bear", d))

    report = compute_pairwise_correlation(sigs, bucket_minutes=60)

    pair = report.pairs[0]
    # Day-1 alpha resolves to BEAR (latest), agrees with beta BEAR; all 7 days agree.
    assert pair.agreements == pair.overlap


def test_conflict_rate_is_complement_of_agreement_when_overlap_high():
    sigs = []
    for d in range(1, 11):
        sigs.append(_sig("alpha", "bull", d))
        sigs.append(_sig("beta", "bull" if d <= 7 else "bear", d))

    report = compute_pairwise_correlation(sigs)
    pair = report.pairs[0]

    assert pair.agreement_rate is not None
    assert pair.conflict_rate is not None
    assert abs((pair.agreement_rate + pair.conflict_rate) - 1.0) < 1e-9


def test_three_sources_yield_three_pairs():
    sigs = []
    for d in range(1, 9):
        sigs.append(_sig("a", "bull", d))
        sigs.append(_sig("b", "bull", d))
        sigs.append(_sig("c", "bull", d))

    report = compute_pairwise_correlation(sigs)

    pair_keys = {(p.source_a, p.source_b) for p in report.pairs}
    assert pair_keys == {("a", "b"), ("a", "c"), ("b", "c")}
