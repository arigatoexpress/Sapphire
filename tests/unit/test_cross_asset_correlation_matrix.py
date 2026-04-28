from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lib.cross_asset.correlation_matrix import (
    MAX_ASSETS_HARD,
    build_correlation_matrix,
    coerce_close_series,
    correlation_for_method,
    detect_breakdown_events,
    kendall,
    normalize_windows,
    pearson,
    spearman,
)

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _series(values: list[float], *, prefix: str = "2026-04-") -> list[dict[str, float | str]]:
    return [{"timestamp": f"{prefix}{idx + 1:02d}T00:00:00Z", "close": value} for idx, value in enumerate(values)]


def test_pearson_perfect_positive() -> None:
    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)


def test_pearson_perfect_negative() -> None:
    assert pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_constant_series_returns_none() -> None:
    assert pearson([1, 1, 1], [1, 2, 3]) is None


def test_spearman_monotonic_nonlinear_is_one() -> None:
    assert spearman([1, 2, 3, 4], [1, 4, 9, 16]) == pytest.approx(1.0)


def test_spearman_handles_ties_with_average_ranks() -> None:
    value = spearman([1, 1, 2, 3], [1, 2, 2, 4])
    assert value is not None
    assert 0.7 < value < 1.0


def test_kendall_perfect_positive() -> None:
    assert kendall([1, 2, 3, 4], [4, 5, 6, 7]) == pytest.approx(1.0)


def test_kendall_perfect_negative() -> None:
    assert kendall([1, 2, 3, 4], [7, 6, 5, 4]) == pytest.approx(-1.0)


def test_kendall_ties_stays_bounded() -> None:
    value = kendall([1, 1, 2, 3], [3, 2, 2, 1])
    assert value is not None
    assert -1.0 <= value <= 1.0


def test_correlation_for_method_rejects_unknown_method() -> None:
    with pytest.raises(ValueError):
        correlation_for_method("magic", [1, 2], [1, 2])


def test_coerce_close_series_accepts_plain_numbers() -> None:
    assert coerce_close_series([10, 11, 12]) == {
        "000000000000": 10.0,
        "000000000001": 11.0,
        "000000000002": 12.0,
    }


def test_coerce_close_series_accepts_mapping_of_values() -> None:
    assert coerce_close_series({"t1": 1, "t2": 2.5}) == {"t1": 1.0, "t2": 2.5}


def test_coerce_close_series_skips_nan_and_missing_close() -> None:
    rows = [{"timestamp": "a", "close": 1.0}, {"timestamp": "b"}, {"timestamp": "c", "close": float("nan")}]
    assert coerce_close_series(rows) == {"a": 1.0}


def test_normalize_windows_from_sequence() -> None:
    assert normalize_windows([3, 5]) == {"3obs": 3, "5obs": 5}


def test_normalize_windows_rejects_tiny_window() -> None:
    with pytest.raises(ValueError):
        normalize_windows({"bad": 1})


def test_build_matrix_is_symmetric_with_diagonal_one() -> None:
    matrix = build_correlation_matrix(
        {"ETH": _series([2, 4, 6, 8]), "BTC": _series([1, 2, 3, 4])},
        windows={"4obs": 4},
        min_observations=2,
        now=FROZEN_NOW,
    )
    selected = matrix.matrix_for(window="4obs", method="pearson")
    assert selected.assets == ["BTC", "ETH"]
    assert selected.matrix[0][0] == 1.0
    assert selected.matrix[1][1] == 1.0
    assert selected.matrix[0][1] == selected.matrix[1][0] == pytest.approx(1.0)


def test_build_matrix_computes_all_methods() -> None:
    matrix = build_correlation_matrix(
        {"A": _series([1, 2, 3, 4]), "B": _series([1, 4, 9, 16])},
        windows={"4obs": 4},
        min_observations=2,
        now=FROZEN_NOW,
    )
    assert matrix.matrix_for(window="4obs", method="pearson").matrix[0][1] < 1.0
    assert matrix.matrix_for(window="4obs", method="spearman").matrix[0][1] == pytest.approx(1.0)
    assert matrix.matrix_for(window="4obs", method="kendall").matrix[0][1] == pytest.approx(1.0)


def test_window_too_short_returns_none_for_pair() -> None:
    matrix = build_correlation_matrix(
        {"A": _series([1, 2]), "B": _series([1, 2])},
        windows={"5obs": 5},
        min_observations=3,
        now=FROZEN_NOW,
    )
    assert matrix.matrix_for(window="5obs", method="pearson").matrix[0][1] is None


def test_partial_timestamp_overlap_uses_shared_samples_only() -> None:
    matrix = build_correlation_matrix(
        {
            "A": [{"timestamp": "1", "close": 1}, {"timestamp": "2", "close": 2}, {"timestamp": "3", "close": 3}],
            "B": [{"timestamp": "2", "close": 2}, {"timestamp": "3", "close": 3}, {"timestamp": "4", "close": 4}],
        },
        windows={"3obs": 3},
        min_observations=2,
        now=FROZEN_NOW,
    )
    selected = matrix.matrix_for(window="3obs", method="pearson")
    assert selected.sample_counts[0][1] == 2
    assert selected.matrix[0][1] == pytest.approx(1.0)


def test_asset_cap_is_enforced() -> None:
    payload = {f"A{i}": _series([1, 2, 3]) for i in range(MAX_ASSETS_HARD + 1)}
    with pytest.raises(ValueError):
        build_correlation_matrix(payload, windows={"3obs": 3}, min_observations=2)


def test_pair_cells_include_each_pair_per_window() -> None:
    matrix = build_correlation_matrix(
        {"A": _series([1, 2, 3]), "B": _series([1, 2, 3]), "C": _series([3, 2, 1])},
        windows={"3obs": 3, "2obs": 2},
        min_observations=2,
        now=FROZEN_NOW,
    )
    assert len(matrix.pair_cells) == 6


def test_matrix_for_raises_on_missing_window() -> None:
    matrix = build_correlation_matrix(
        {"A": _series([1, 2, 3]), "B": _series([1, 2, 3])},
        windows={"3obs": 3},
        min_observations=2,
        now=FROZEN_NOW,
    )
    with pytest.raises(KeyError):
        matrix.matrix_for(window="absent", method="pearson")


def test_breakdown_events_detect_large_correlation_move() -> None:
    xs = list(range(70))
    ys = [x + ((x % 5) * 0.01) for x in xs[:60]] + [200 - x for x in xs[60:]]
    events = detect_breakdown_events(
        {"A": coerce_close_series(_series(xs)), "B": coerce_close_series(_series(ys))},
        window=5,
        baseline_window=40,
        z_threshold=0.5,
        min_baseline_observations=5,
    )
    assert events
    assert events[0].direction == "correlation_breakdown"
    assert events[0].severity in {"moderate", "high", "severe"}


def test_build_matrix_includes_breakdown_events() -> None:
    xs = list(range(80))
    ys = [x + ((x % 3) * 0.02) for x in xs[:70]] + [300 - x for x in xs[70:]]
    matrix = build_correlation_matrix(
        {"A": _series(xs), "B": _series(ys)},
        windows={"10obs": 10},
        min_observations=2,
        breakdown_window=5,
        baseline_window=40,
        breakdown_z_threshold=0.5,
        now=FROZEN_NOW,
    )
    assert matrix.breakdown_events


def test_matrix_output_is_deterministic_for_fixed_inputs_and_time() -> None:
    payload = {"A": _series([1, 2, 3, 4]), "B": _series([4, 3, 2, 1])}
    first = build_correlation_matrix(payload, windows={"4obs": 4}, min_observations=2, now=FROZEN_NOW)
    second = build_correlation_matrix(payload, windows={"4obs": 4}, min_observations=2, now=FROZEN_NOW)
    assert first.to_dict() == second.to_dict()
