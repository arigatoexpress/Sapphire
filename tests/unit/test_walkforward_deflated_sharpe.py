"""Unit tests for lib/analytics/walkforward/deflated_sharpe.py.

Covers the wrapper around the existing ``lib.analytics.deflated_sharpe`` module.
The base module is treated as read-only; we verify only the wrapper's behaviour
on top.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.deflated_sharpe import DSRResult  # noqa: E402
from lib.analytics.walkforward.deflated_sharpe import (  # noqa: E402
    WalkforwardDSRResult,
    _coerce_sharpes,
    deflated_sharpe_for_walkforward,
    sample_kurtosis,
    sample_skewness,
)

# ── moment estimators ──────────────────────────────────────────────────────


def test_sample_skewness_zero_for_symmetric_distribution() -> None:
    sym = [-2, -1, 0, 1, 2]
    assert sample_skewness(sym) == pytest.approx(0.0, abs=1e-9)


def test_sample_skewness_positive_for_right_skewed() -> None:
    right = [0, 0, 0, 1, 5]
    assert sample_skewness(right) > 0.5


def test_sample_skewness_negative_for_left_skewed() -> None:
    left = [-5, -1, 0, 0, 0]
    assert sample_skewness(left) < -0.5


def test_sample_skewness_zero_for_too_few_observations() -> None:
    assert sample_skewness([]) == 0.0
    assert sample_skewness([1.0]) == 0.0


def test_sample_kurtosis_about_three_for_uniform_normalish_set() -> None:
    """Approximately Gaussian sample → kurtosis ≈ 3."""
    # Symmetric small set close to normal moments
    xs = [-2, -1, -0.5, 0, 0, 0.5, 1, 2]
    k = sample_kurtosis(xs)
    # Loose check: between 1 and 5; not exactly 3 because n is small
    assert 1.0 < k < 5.0


def test_sample_kurtosis_default_three_for_too_few_obs() -> None:
    assert sample_kurtosis([]) == 3.0
    assert sample_kurtosis([1.0]) == 3.0


# ── _coerce_sharpes ────────────────────────────────────────────────────────


def test_coerce_sharpes_drops_none_and_nan() -> None:
    out = _coerce_sharpes([1.5, None, float("nan"), 0.7, "junk", 2.1])
    assert out == [1.5, 0.7, 2.1]


def test_coerce_sharpes_handles_empty() -> None:
    assert _coerce_sharpes([]) == []


# ── deflated_sharpe_for_walkforward — wrapper behaviour ────────────────────


class _FakeWindow:
    def __init__(self, test_sharpe: float) -> None:
        self.test_sharpe = test_sharpe


class _FakeWFResult:
    def __init__(self, sharpes: list[float], rets: list[float]) -> None:
        self.strategy_cls = "FakeStrategy"
        self.symbol = "BTC-USD"
        self.windows = [_FakeWindow(s) for s in sharpes]
        self.concatenated_test_returns = list(rets)


def test_deflated_for_walkforward_returns_wrapped_dsr() -> None:
    wf = _FakeWFResult([1.5, 1.2, 1.8, 0.5], [0.01, -0.02, 0.03, 0.005] * 60)
    result = deflated_sharpe_for_walkforward(wf)
    assert isinstance(result, WalkforwardDSRResult)
    assert isinstance(result.base, DSRResult)
    assert result.n_windows == 4


def test_deflated_for_walkforward_picks_max_sharpe_by_default() -> None:
    wf = _FakeWFResult([0.1, 0.5, 1.5, 0.3], [0.01] * 100)
    result = deflated_sharpe_for_walkforward(wf)
    assert result.selected_sharpe == 1.5


def test_deflated_for_walkforward_explicit_selected() -> None:
    wf = _FakeWFResult([0.1, 0.5, 1.5, 0.3], [0.01] * 100)
    result = deflated_sharpe_for_walkforward(wf, selected_sharpe=0.5)
    assert result.selected_sharpe == 0.5


def test_deflated_for_walkforward_uses_oos_n_obs() -> None:
    wf = _FakeWFResult([1.0, 1.2], [0.01] * 250)
    result = deflated_sharpe_for_walkforward(wf)
    assert result.n_obs_oos == 250


def test_deflated_n_obs_override_takes_precedence() -> None:
    wf = _FakeWFResult([1.0, 1.2], [0.01] * 250)
    result = deflated_sharpe_for_walkforward(wf, n_obs_override=42)
    assert result.n_obs_oos == 250  # provenance unchanged
    # The base DSR's correction was computed with n_obs=42 — we can verify by
    # computing the expected probability with explicit 42.
    from lib.analytics.deflated_sharpe import deflated_sharpe_ratio

    expected = deflated_sharpe_ratio(
        result.window_sharpes,
        selected_sharpe=result.selected_sharpe,
        skewness=result.skewness,
        kurtosis=result.kurtosis,
        n_obs=42,
        threshold=result.threshold,
    )
    assert result.base.probability == pytest.approx(expected.probability)


def test_deflated_threshold_override_propagates() -> None:
    wf = _FakeWFResult([1.0, 1.5], [0.01] * 100)
    result = deflated_sharpe_for_walkforward(wf, threshold=0.99)
    assert result.threshold == 0.99


def test_deflated_with_explicit_window_sharpes() -> None:
    result = deflated_sharpe_for_walkforward(
        walkforward_result=None,
        window_sharpes=[1.0, 1.2, 0.8, 1.5],
        test_returns=[0.01, -0.02, 0.005] * 30,
    )
    assert result.n_windows == 4
    assert result.window_sharpes == [1.0, 1.2, 0.8, 1.5]


def test_deflated_handles_no_inputs_gracefully() -> None:
    result = deflated_sharpe_for_walkforward()
    # Should not raise; returns a degenerate placeholder result.
    assert isinstance(result, WalkforwardDSRResult)
    assert result.n_windows == 0
    assert "degenerate" in result.note


def test_deflated_passed_property_proxies_base() -> None:
    wf = _FakeWFResult([5.0] * 5, [0.05] * 252)  # very high sharpes — should pass
    result = deflated_sharpe_for_walkforward(wf, threshold=0.01)
    assert result.passed is True


def test_deflated_to_dict_is_jsonable() -> None:
    import json

    wf = _FakeWFResult([1.0, 1.2, 0.8], [0.01, -0.02] * 50)
    result = deflated_sharpe_for_walkforward(wf)
    d = result.to_dict()
    blob = json.dumps(d)
    parsed = json.loads(blob)
    assert "deflated_sharpe" in parsed
    assert "selected_sharpe" in parsed
    assert "n_windows" in parsed


def test_deflated_skewness_kurtosis_computed_from_returns() -> None:
    """Returns with strong negative skew should yield negative skewness."""
    rets = [-0.10, -0.08, 0.005, 0.005, 0.005, 0.005, 0.005]
    wf = _FakeWFResult([1.0], rets * 5)
    result = deflated_sharpe_for_walkforward(wf)
    assert result.skewness < 0


def test_deflated_handles_single_window() -> None:
    wf = _FakeWFResult([1.5], [0.01] * 100)
    result = deflated_sharpe_for_walkforward(wf)
    assert result.n_windows == 1
    # base.trials = len(sharpe_list) = 1 → expected_max_sharpe degenerates to
    # the lone Sharpe; deflated → 0; probability is around 0.5.
    assert 0.3 <= result.base.probability <= 0.7


def test_deflated_does_not_mutate_base_module(monkeypatch) -> None:
    """Smoke check — calling the wrapper does not redefine
    ``lib.analytics.deflated_sharpe.deflated_sharpe_ratio``."""
    import lib.analytics.deflated_sharpe as dsr_mod

    original = dsr_mod.deflated_sharpe_ratio
    wf = _FakeWFResult([1.0, 1.2], [0.01] * 50)
    deflated_sharpe_for_walkforward(wf)
    assert dsr_mod.deflated_sharpe_ratio is original


def test_walkforward_dsr_proxy_properties() -> None:
    base = DSRResult(
        sharpe=1.5,
        deflated_sharpe=0.7,
        probability=0.95,
        trials=5,
        passed=True,
    )
    wf = WalkforwardDSRResult(
        base=base,
        n_windows=5,
        n_obs_oos=200,
        window_sharpes=[1.5, 1.2, 0.8, 1.0, 1.3],
        skewness=-0.1,
        kurtosis=3.2,
        selected_sharpe=1.5,
        threshold=0.95,
    )
    assert wf.passed is True
    assert wf.probability == 0.95
    assert wf.deflated_sharpe == 0.7
    assert wf.trials == 5


def test_deflated_window_sharpes_dropping_nan() -> None:
    wf = _FakeWFResult([1.5, float("nan"), 0.8], [0.01] * 100)
    result = deflated_sharpe_for_walkforward(wf)
    # NaN should be dropped, leaving 2 sharpes
    assert result.window_sharpes == [1.5, 0.8]


def test_deflated_records_provenance_note() -> None:
    wf = _FakeWFResult([1.0, 1.2], [0.01] * 100)
    result = deflated_sharpe_for_walkforward(wf)
    assert "FakeStrategy" in result.note
    assert "BTC-USD" in result.note


def test_deflated_explicit_inputs_record_note() -> None:
    result = deflated_sharpe_for_walkforward(
        window_sharpes=[1.0, 1.2], test_returns=[0.01] * 100
    )
    assert "explicit window_sharpes" in result.note
