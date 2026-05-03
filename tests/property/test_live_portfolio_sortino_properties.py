"""Property-based tests for ``lib.live_portfolio.sortino``.

The Sortino ratio gates every live-capital ramp-up rung. A subtle bug here
would either advance live capital prematurely or stall the ramp on a
correctly performing strategy. Properties below pin the contract:

* **Manual-formula agreement**: the ``value`` field matches an independent
  computation to ``1e-6`` relative tolerance.
* **Small-sample handling**: fewer than ``minimum_periods`` observations
  always yields ``value=None`` with a ``reason`` that names the shortfall.
* **All-zero handling**: a series of zeros never raises and returns the
  documented ``no_downside_no_positive_excess`` reason.
* **Deterministic**: same input → same SortinoResult fields.
* **Skip semantics**: NaN / unparsable inputs increment ``skipped`` instead
  of contaminating the ratio.

The reference implementation in this test file is a from-scratch port of
the formula in the docstring, written without looking at the production
code's ordering. Differences ≥ ``1e-6`` indicate a real bug.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.property  # noqa: E402, F401
from lib.live_portfolio.sortino import (  # noqa: E402
    SortinoResult,
    last_n_sortino,
    sortino_ratio,
)

# ---------------------------------------------------------------------------
# Reference implementation — independent of the production code path
# ---------------------------------------------------------------------------


def _reference_sortino(
    returns: list[float], target: float = 0.0
) -> tuple[float | None, float, float]:
    """Independent reimplementation. Returns (value, downside_dev, mean_return)."""
    if not returns:
        return None, 0.0, 0.0
    mean_return = sum(returns) / len(returns)
    excesses = [r - target for r in returns]
    mean_excess = sum(excesses) / len(returns)
    downside = [min(0.0, r - target) ** 2 for r in returns]
    dd = math.sqrt(sum(downside) / len(returns))
    if dd == 0:
        if mean_excess > 0:
            return math.inf, 0.0, mean_return
        return None, 0.0, mean_return
    return mean_excess / dd, dd, mean_return


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Returns: realistic per-period return decimals between -50 % and +50 %.
_returns = st.floats(
    min_value=-0.5,
    max_value=0.5,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)

_min_periods_strategy = st.integers(min_value=1, max_value=20)


# ---------------------------------------------------------------------------
# 1. Manual-formula agreement to 1e-6
# ---------------------------------------------------------------------------


@given(st.lists(_returns, min_size=14, max_size=200))
@hyp_settings(suppress_health_check=[HealthCheck.too_slow])
def test_sortino_matches_reference_to_one_part_in_a_million(
    returns: list[float],
) -> None:
    result = sortino_ratio(returns, minimum_periods=14)
    expected_value, expected_dd, expected_mean = _reference_sortino(returns, 0.0)

    if expected_value is None:
        assert result.value is None, (
            f"reference says value=None, got {result.value} for {returns!r}"
        )
        return
    if expected_value == math.inf:
        assert result.value == math.inf
        return
    assert result.value is not None
    assert math.isclose(result.value, expected_value, rel_tol=1e-6, abs_tol=1e-9), (
        f"value mismatch: ours={result.value} ref={expected_value} for n={len(returns)}"
    )
    if result.downside_deviation is not None:
        assert math.isclose(result.downside_deviation, expected_dd, rel_tol=1e-9, abs_tol=1e-12)
    if result.mean_return is not None:
        assert math.isclose(result.mean_return, expected_mean, rel_tol=1e-9, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 2. Small-sample handling
# ---------------------------------------------------------------------------


@given(
    st.lists(_returns, min_size=0, max_size=13),
    st.integers(min_value=14, max_value=30),
)
def test_sortino_rejects_short_series_below_minimum(returns: list[float], minimum: int) -> None:
    result = sortino_ratio(returns, minimum_periods=minimum)
    assert result.value is None
    assert result.reason.startswith("insufficient_periods:")


# ---------------------------------------------------------------------------
# 3. All-zero handling
# ---------------------------------------------------------------------------


@given(st.integers(min_value=14, max_value=200))
def test_sortino_all_zero_returns_no_positive_excess(n: int) -> None:
    returns = [0.0] * n
    result = sortino_ratio(returns, minimum_periods=14)
    assert result.value is None
    assert result.reason == "no_downside_no_positive_excess"
    assert result.downside_deviation == 0.0


# ---------------------------------------------------------------------------
# 4. All-positive returns above target → infinite Sortino
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.floats(min_value=1e-6, max_value=0.5, allow_nan=False, allow_infinity=False),
        min_size=14,
        max_size=200,
    )
)
def test_sortino_all_positive_returns_infinite(returns: list[float]) -> None:
    result = sortino_ratio(returns, minimum_periods=14)
    assert result.value == math.inf
    assert result.reason == "no_downside_positive_mean"
    assert result.downside_deviation == 0.0


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


@given(st.lists(_returns, min_size=14, max_size=120))
def test_sortino_deterministic(returns: list[float]) -> None:
    a = sortino_ratio(returns, minimum_periods=14)
    b = sortino_ratio(returns, minimum_periods=14)
    assert a == b


# ---------------------------------------------------------------------------
# 6. NaN / unparsable inputs increment skipped, never propagate
# ---------------------------------------------------------------------------


@given(
    st.lists(_returns, min_size=14, max_size=120),
    st.lists(
        st.sampled_from([float("nan"), "not-a-number", None, "x"]),
        min_size=0,
        max_size=10,
    ),
)
def test_sortino_skips_unparsable_without_raising(
    returns: list[float],
    junk: list,
) -> None:
    polluted = list(returns) + junk  # type: ignore[arg-type]
    result = sortino_ratio(polluted, minimum_periods=14)
    # Either the cleaned series still has 14 entries (and we get a value)
    # or the cleaned series is short (and we get insufficient_periods).
    assert result.skipped == len(junk)
    if len(returns) >= 14:
        assert result.periods == len(returns)


# ---------------------------------------------------------------------------
# 7. Annualisation factor — multiplier is sqrt(factor)
# ---------------------------------------------------------------------------


@given(
    st.lists(_returns, min_size=14, max_size=80).filter(
        # Avoid the all-zero / all-positive branches; we want a finite ratio.
        lambda xs: any(r < 0 for r in xs) and any(r > 0 for r in xs)
    ),
    st.floats(min_value=1.0, max_value=365.0, allow_nan=False, allow_infinity=False),
)
def test_sortino_annualisation_factor_applies_sqrt(returns: list[float], factor: float) -> None:
    base = sortino_ratio(returns, minimum_periods=14)
    annualised = sortino_ratio(returns, minimum_periods=14, annualization_factor=factor)
    if base.value is None or base.value == math.inf:
        return
    assert annualised.value is not None
    expected = base.value * math.sqrt(factor)
    assert math.isclose(annualised.value, expected, rel_tol=1e-9, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 8. last_n_sortino window — only uses tail
# ---------------------------------------------------------------------------


@given(
    st.lists(_returns, min_size=14, max_size=200),
    st.lists(
        _returns,
        min_size=14,
        max_size=14,
    ),
)
def test_last_n_sortino_uses_only_tail(head: list[float], tail: list[float]) -> None:
    """The result of last_n_sortino on (head + tail) equals sortino on tail alone."""
    combined = list(head) + list(tail)
    last = last_n_sortino(combined, window=14)
    direct = sortino_ratio(tail, minimum_periods=14)
    # Compare value, downside_deviation, mean_return — skipped will differ
    # because last_n_sortino aggregates skipped from both passes.
    assert last.value == direct.value
    if last.downside_deviation is not None and direct.downside_deviation is not None:
        assert math.isclose(last.downside_deviation, direct.downside_deviation, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 9. SortinoResult shape — to_dict always serializable
# ---------------------------------------------------------------------------


@given(st.lists(_returns, min_size=0, max_size=200))
def test_sortino_result_to_dict_serializable(returns: list[float]) -> None:
    import json

    result = sortino_ratio(returns, minimum_periods=14)
    data = result.to_dict()
    # to_dict must be JSON-safe; inf is mapped to literal "inf".
    payload = json.dumps(data)
    assert isinstance(payload, str)
    assert "value" in data
    assert "periods" in data
    assert isinstance(result, SortinoResult)
