from __future__ import annotations

import math

from lib.live_portfolio.sortino import last_n_sortino, sortino_ratio


def test_sortino_rejects_single_data_point() -> None:
    result = sortino_ratio([0.01], minimum_periods=14)
    assert result.value is None
    assert "insufficient_periods" in result.reason


def test_sortino_rejects_small_sample() -> None:
    result = sortino_ratio([0.01] * 13, minimum_periods=14)
    assert result.periods == 13
    assert result.value is None


def test_sortino_handles_nan_by_skipping() -> None:
    result = sortino_ratio([0.01] * 14 + [float("nan")], minimum_periods=14)
    assert result.skipped == 1
    assert math.isinf(result.value or 0)


def test_sortino_all_positive_is_infinite() -> None:
    result = sortino_ratio([0.01] * 14, minimum_periods=14)
    assert result.reason == "no_downside_positive_mean"
    assert math.isinf(result.value or 0)


def test_sortino_all_zero_returns_none() -> None:
    result = sortino_ratio([0.0] * 14, minimum_periods=14)
    assert result.value is None
    assert result.reason == "no_downside_no_positive_excess"


def test_sortino_matches_manual_reference() -> None:
    returns = [0.02, -0.01, 0.015, -0.02, 0.01, 0.005, -0.005] * 2
    mean = sum(returns) / len(returns)
    downside = math.sqrt(sum(min(0.0, r) ** 2 for r in returns) / len(returns))
    expected = mean / downside
    result = sortino_ratio(returns, minimum_periods=14)
    assert result.value is not None
    assert result.value == expected


def test_sortino_target_return_changes_result() -> None:
    returns = [0.02, -0.01, 0.015, -0.02, 0.01, 0.005, -0.005] * 2
    zero = sortino_ratio(returns, minimum_periods=14).value
    target = sortino_ratio(returns, minimum_periods=14, target_return=0.001).value
    assert target != zero


def test_sortino_annualization_factor() -> None:
    returns = [0.02, -0.01, 0.015, -0.02, 0.01, 0.005, -0.005] * 2
    base = sortino_ratio(returns, minimum_periods=14).value
    ann = sortino_ratio(returns, minimum_periods=14, annualization_factor=4).value
    assert ann == (base or 0) * 2


def test_last_n_sortino_uses_tail_window() -> None:
    returns = [-0.5] * 14 + [0.01] * 14
    result = last_n_sortino(returns, window=14)
    assert math.isinf(result.value or 0)


def test_sortino_string_numbers_are_accepted() -> None:
    returns = ["0.02", "-0.01"] * 7
    assert sortino_ratio(returns, minimum_periods=14).periods == 14


def test_sortino_bad_values_are_skipped() -> None:
    returns = ["bad", None, "0.02", "-0.01"] * 7
    result = sortino_ratio(returns, minimum_periods=14)
    assert result.periods == 14
    assert result.skipped == 14


def test_sortino_to_dict_serializes_infinity() -> None:
    result = sortino_ratio([0.01] * 14, minimum_periods=14).to_dict()
    assert result["value"] == "inf"
