"""GMM-based regime detection for crypto markets.

Fits a Gaussian Mixture Model on rolling return/volatility/volume features
to classify the market into interpretable regimes:

  2-state: trend  |  mean_reverting
  3-state: trend  |  mean_reverting  |  crisis

State labels are assigned by ranking component means on the log-return feature
(highest → trend, lowest → crisis/mean_reverting), so they are invariant to
GMM initialization order.

Requires scikit-learn. Degrades gracefully if unavailable.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from lib.analytics.backtest_engine import Bar

try:
    import numpy as np
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


# ── Feature extraction ─────────────────────────────────────────────────────────

_WINDOW = 20  # rolling window for all features


def _log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev > 0:
            out.append(math.log(closes[i] / prev))
        else:
            out.append(0.0)
    return out


def _realized_vol(log_rets: list[float], window: int) -> list[float | None]:
    """Rolling std of log returns over ``window``."""
    out: list[float | None] = []
    for i in range(len(log_rets)):
        if i < window - 1:
            out.append(None)
        else:
            chunk = log_rets[i - window + 1 : i + 1]
            mean = sum(chunk) / window
            var = sum((r - mean) ** 2 for r in chunk) / window
            out.append(math.sqrt(var))
    return out


def _volume_zscore(volumes: list[float], window: int) -> list[float | None]:
    """Rolling z-score of volume."""
    out: list[float | None] = []
    for i in range(len(volumes)):
        if i < window - 1:
            out.append(None)
        else:
            chunk = volumes[i - window + 1 : i + 1]
            mean = sum(chunk) / window
            std = math.sqrt(sum((v - mean) ** 2 for v in chunk) / window)
            out.append((volumes[i] - mean) / std if std > 0 else 0.0)
    return out


def _rolling_skew(log_rets: list[float], window: int) -> list[float | None]:
    """Rolling skewness of log returns."""
    out: list[float | None] = []
    for i in range(len(log_rets)):
        if i < window - 1:
            out.append(None)
        else:
            chunk = log_rets[i - window + 1 : i + 1]
            n = len(chunk)
            mean = sum(chunk) / n
            m2 = sum((r - mean) ** 2 for r in chunk) / n
            m3 = sum((r - mean) ** 3 for r in chunk) / n
            if m2 > 0:
                out.append(m3 / (m2**1.5))
            else:
                out.append(0.0)
    return out


def extract_features(bars: list[Bar]) -> list[list[float]]:
    """Extract (mean_log_ret, realized_vol, vol_zscore, skewness) feature rows.

    Returns only rows where all four features are available (i.e. bars[window-1:]).
    Each row: [mean_return_20d, realized_vol_20d, volume_zscore_20d, skewness_20d].
    """
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    log_rets = _log_returns(closes)

    # log_rets has len(bars)-1 elements; align volume/bars to same length
    vols_aligned = volumes[1:]  # drop first bar to match log_rets length
    rv = _realized_vol(log_rets, _WINDOW)
    vz = _volume_zscore(vols_aligned, _WINDOW)
    sk = _rolling_skew(log_rets, _WINDOW)

    # Rolling mean return over window
    mean_rets: list[float | None] = []
    for i in range(len(log_rets)):
        if i < _WINDOW - 1:
            mean_rets.append(None)
        else:
            chunk = log_rets[i - _WINDOW + 1 : i + 1]
            mean_rets.append(sum(chunk) / _WINDOW)

    rows: list[list[float]] = []
    for mr, r, v, s in zip(mean_rets, rv, vz, sk, strict=False):
        if mr is None or r is None or v is None or s is None:
            continue
        rows.append([mr, r, v, s])
    return rows


# ── GMM Regime Detector ────────────────────────────────────────────────────────


@dataclass
class RegimePrediction:
    state: str  # trend | mean_reverting | crisis
    prob: float  # probability of the current state (0–1)
    trend_prob: float
    mean_reverting_prob: float
    crisis_prob: float | None = None  # only populated for 3-state model
    n_components: int = 2


class GMMRegimeDetector:
    """Fits a GMM on historical bar features and predicts the current regime.

    Usage::

        detector = GMMRegimeDetector(n_components=3)
        bars = fetch_ohlcv("BTC-USD", days=90)
        prediction = detector.predict(bars)
        print(prediction.state, prediction.prob)

    The detector auto-caches predictions per symbol with a configurable TTL.
    Call ``get_regime(symbol)`` for the SignalEnhancer integration path.
    """

    CACHE_TTL_SECS = 300  # 5 minutes

    def __init__(self, n_components: int = 3, random_state: int = 42) -> None:
        if not _HAS_SKLEARN:
            raise ImportError(
                "scikit-learn is required for GMMRegimeDetector: pip install scikit-learn"
            )
        if n_components not in (2, 3):
            raise ValueError("n_components must be 2 or 3")

        self._n = n_components
        self._rs = random_state
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[RegimePrediction, float]] = {}  # sym → (pred, ts)

    # ------------------------------------------------------------------

    def fit_predict(self, bars: list[Bar]) -> RegimePrediction:
        """Fit GMM on bar features and predict the most recent regime.

        Fits on all feature rows except the last, then predicts on the last row
        (current window). Returns ``None``-safe fallback for insufficient data.
        """
        rows = extract_features(bars)
        if len(rows) < self._n * 5:
            log.debug("GMM: insufficient feature rows (%d) for %d components", len(rows), self._n)
            return self._fallback()

        X = np.array(rows, dtype=float)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        gmm = GaussianMixture(
            n_components=self._n,
            covariance_type="full",
            n_init=3,
            random_state=self._rs,
        )
        gmm.fit(X_scaled)

        labels = self._assign_labels(gmm)
        probs = gmm.predict_proba(X_scaled[-1:]).flatten()  # shape (n_components,)

        # Map component index → label probabilities
        label_probs: dict[str, float] = {label: 0.0 for label in labels.values()}
        for comp_idx, label in labels.items():
            label_probs[label] = float(probs[comp_idx])

        best_comp = int(np.argmax(probs))
        current_state = labels[best_comp]

        return RegimePrediction(
            state=current_state,
            prob=round(float(probs[best_comp]), 3),
            trend_prob=round(label_probs.get("trend", 0.0), 3),
            mean_reverting_prob=round(label_probs.get("mean_reverting", 0.0), 3),
            crisis_prob=round(label_probs.get("crisis", 0.0), 3) if self._n == 3 else None,
            n_components=self._n,
        )

    def _assign_labels(self, gmm: Any) -> dict[int, str]:
        """Assign semantic labels by ranking component means on the return feature."""
        means = gmm.means_[:, 0]  # feature 0 = mean log return
        sorted_comps = list(np.argsort(means))  # ascending: low-return → high-return
        if self._n == 2:
            return {sorted_comps[0]: "mean_reverting", sorted_comps[1]: "trend"}
        # 3-state
        return {
            sorted_comps[0]: "crisis",
            sorted_comps[1]: "mean_reverting",
            sorted_comps[2]: "trend",
        }

    def _fallback(self) -> RegimePrediction:
        return RegimePrediction(
            state="unknown",
            prob=0.0,
            trend_prob=0.0,
            mean_reverting_prob=0.0,
            crisis_prob=0.0 if self._n == 3 else None,
            n_components=self._n,
        )

    # ------------------------------------------------------------------

    def get_regime(self, symbol: str, days: int = 90) -> RegimePrediction | None:
        """Fetch recent bars for ``symbol`` and return cached regime prediction.

        Returns None if bars cannot be fetched or sklearn is unavailable.
        """
        now = time.time()
        with self._lock:
            cached = self._cache.get(symbol)
            if cached and (now - cached[1]) < self.CACHE_TTL_SECS:
                return cached[0]

        try:
            from lib.analytics.backtest_engine import fetch_ohlcv

            bars = fetch_ohlcv(symbol, days=days)
            pred = self.fit_predict(bars)
            with self._lock:
                self._cache[symbol] = (pred, now)
            return pred
        except Exception as e:
            log.debug("GMM regime fetch failed for %s: %s", symbol, e)
            return None


# ── Module-level singleton ─────────────────────────────────────────────────────

_detector: GMMRegimeDetector | None = None
_detector_lock = threading.Lock()


def get_detector(n_components: int = 3) -> GMMRegimeDetector | None:
    """Return a module-level GMMRegimeDetector singleton, or None if sklearn missing."""
    global _detector
    if not _HAS_SKLEARN:
        return None
    with _detector_lock:
        if _detector is None:
            try:
                _detector = GMMRegimeDetector(n_components=n_components)
            except Exception as e:
                log.debug("GMMRegimeDetector init failed: %s", e)
                return None
    return _detector


__all__ = [
    "GMMRegimeDetector",
    "RegimePrediction",
    "extract_features",
    "get_detector",
]
