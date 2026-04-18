"""Unit tests for lib/analytics/regime.py (GMM regime detection)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.backtest_engine import _synthetic_bars  # noqa: E402
from lib.analytics.regime import (  # noqa: E402
    RegimePrediction,
    extract_features,
    get_detector,
)

sklearn_available = pytest.importorskip(
    "sklearn", reason="scikit-learn not installed — skipping GMM tests"
)


# ── Feature extraction ─────────────────────────────────────────────────────────


def test_extract_features_output_shape() -> None:
    bars = _synthetic_bars("BTC", 60)
    rows = extract_features(bars)
    # Need at least window bars worth of data (window=20), features start at bar 21
    assert len(rows) > 0
    assert all(len(row) == 4 for row in rows), "each row should have 4 features"


def test_extract_features_insufficient_bars() -> None:
    bars = _synthetic_bars("BTC", 5)
    rows = extract_features(bars)
    # Too few bars for rolling window — expect empty
    assert rows == []


def test_extract_features_values_finite() -> None:
    import math
    bars = _synthetic_bars("BTC", 90)
    rows = extract_features(bars)
    assert rows, "should produce at least some feature rows"
    for row in rows:
        assert all(math.isfinite(v) for v in row), f"NaN/inf in row: {row}"


def test_extract_features_vol_nonnegative() -> None:
    bars = _synthetic_bars("BTC", 60)
    rows = extract_features(bars)
    for row in rows:
        # feature index 1 = realized vol — always >= 0
        assert row[1] >= 0.0, f"realized vol should be non-negative, got {row[1]}"


# ── GMMRegimeDetector ──────────────────────────────────────────────────────────


def test_gmm_detector_2state_fit_predict() -> None:
    from lib.analytics.regime import GMMRegimeDetector

    bars = _synthetic_bars("BTC", 90)
    detector = GMMRegimeDetector(n_components=2)
    pred = detector.fit_predict(bars)

    assert isinstance(pred, RegimePrediction)
    assert pred.state in {"trend", "mean_reverting", "unknown"}
    assert 0.0 <= pred.prob <= 1.0
    assert pred.crisis_prob is None  # 2-state has no crisis


def test_gmm_detector_3state_fit_predict() -> None:
    from lib.analytics.regime import GMMRegimeDetector

    bars = _synthetic_bars("BTC", 90)
    detector = GMMRegimeDetector(n_components=3)
    pred = detector.fit_predict(bars)

    assert isinstance(pred, RegimePrediction)
    assert pred.state in {"trend", "mean_reverting", "crisis", "unknown"}
    assert 0.0 <= pred.prob <= 1.0
    assert pred.crisis_prob is not None


def test_gmm_probabilities_sum_to_one() -> None:
    from lib.analytics.regime import GMMRegimeDetector

    bars = _synthetic_bars("BTC", 90)

    for n in (2, 3):
        detector = GMMRegimeDetector(n_components=n)
        pred = detector.fit_predict(bars)
        if pred.state == "unknown":
            continue
        total = pred.trend_prob + pred.mean_reverting_prob
        if n == 3 and pred.crisis_prob is not None:
            total += pred.crisis_prob
        assert abs(total - 1.0) < 0.01, f"probs should sum to 1 for {n}-state, got {total}"


def test_gmm_detector_fallback_on_insufficient_bars() -> None:
    from lib.analytics.regime import GMMRegimeDetector

    bars = _synthetic_bars("BTC", 10)  # too few for GMM
    detector = GMMRegimeDetector(n_components=2)
    pred = detector.fit_predict(bars)
    assert pred.state == "unknown"
    assert pred.prob == 0.0


def test_gmm_invalid_n_components_raises() -> None:
    from lib.analytics.regime import GMMRegimeDetector

    with pytest.raises(ValueError):
        GMMRegimeDetector(n_components=4)


def test_get_detector_returns_detector_or_none() -> None:
    detector = get_detector()
    # Should return a GMMRegimeDetector if sklearn is available
    from lib.analytics.regime import GMMRegimeDetector

    assert isinstance(detector, GMMRegimeDetector)


def test_gmm_n_components_stored() -> None:
    from lib.analytics.regime import GMMRegimeDetector

    d2 = GMMRegimeDetector(n_components=2)
    d3 = GMMRegimeDetector(n_components=3)
    bars = _synthetic_bars("BTC", 90)
    assert d2.fit_predict(bars).n_components == 2
    assert d3.fit_predict(bars).n_components == 3


def test_gmm_detector_reproducible() -> None:
    """Same seed + same bars should produce the same state."""
    from lib.analytics.regime import GMMRegimeDetector

    bars = _synthetic_bars("BTC", 90)
    d1 = GMMRegimeDetector(n_components=3, random_state=42)
    d2 = GMMRegimeDetector(n_components=3, random_state=42)
    p1 = d1.fit_predict(bars)
    p2 = d2.fit_predict(bars)
    assert p1.state == p2.state
    assert abs(p1.prob - p2.prob) < 1e-6
