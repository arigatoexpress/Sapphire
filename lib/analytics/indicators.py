"""Pure-Python technical indicators — no external dependencies beyond stdlib.

Every function here takes plain lists/sequences of floats and returns floats
or lists of floats. No pandas, no numpy — keeps the analytics layer importable
from constrained environments (Pi workers, CI sandboxes) without dragging in
the scientific Python stack.

Currently exposed:
    compute_true_range(high, low, prev_close) -> float
    compute_atr(highs, lows, closes, period=14) -> float | None
    compute_adx(highs, lows, closes, period=14) -> dict  (adx, plus_di, minus_di)
    classify_adx_regime(adx) -> str  (trending | ranging | transition | unknown)

ADX is the Wilder (1978) Average Directional Index. Implementation follows the
textbook recurrence (Wilder smoothing) rather than a simple moving average —
the latter is a common bug that shifts the ADX by a few bars and weakens the
regime signal.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

# ---------------------------------------------------------------------------
# True Range / ATR
# ---------------------------------------------------------------------------


def compute_true_range(high: float, low: float, prev_close: float) -> float:
    """Wilder True Range = max(H-L, |H-PC|, |L-PC|)."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float | None:
    """Wilder-smoothed Average True Range.

    Returns None if fewer than ``period + 1`` bars are supplied. The first ATR
    seed is the SMA of the first ``period`` TR values; subsequent values use
    Wilder smoothing: ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period.
    """
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None

    trs: list[float] = []
    for i in range(1, n):
        trs.append(compute_true_range(highs[i], lows[i], closes[i - 1]))

    # Seed: simple average of first `period` TRs
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


# ---------------------------------------------------------------------------
# ADX / +DI / -DI
# ---------------------------------------------------------------------------


class ADXResult(TypedDict):
    adx: float
    plus_di: float
    minus_di: float


def compute_adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> ADXResult | None:
    """Wilder Average Directional Index (14-period default).

    Requires at least ``2 * period + 1`` bars to produce a stable ADX (one
    period to seed +DM/-DM smoothing, another to smooth the DX into ADX).
    Returns ``{"adx", "plus_di", "minus_di"}`` as the LATEST values at the
    most recent bar, or None if insufficient data.

    Values:
        adx      — 0..100, strength of trend (direction-agnostic)
        plus_di  — 0..100, positive directional indicator
        minus_di — 0..100, negative directional indicator
    """
    n = len(closes)
    if n < 2 * period + 1 or len(highs) != n or len(lows) != n:
        return None

    # --- Step 1: +DM, -DM, TR series (length n-1) -------------------------
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    trs: list[float] = []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        trs.append(compute_true_range(highs[i], lows[i], closes[i - 1]))

    # --- Step 2: Wilder-smooth each series (first value = sum of first `period`) ---
    # Wilder's recurrence for sums: S_t = S_{t-1} - S_{t-1}/period + X_t
    def wilder_smooth(series: list[float]) -> list[float]:
        out: list[float] = []
        running = sum(series[:period])
        out.append(running)
        for x in series[period:]:
            running = running - (running / period) + x
            out.append(running)
        return out

    sm_plus = wilder_smooth(plus_dm)
    sm_minus = wilder_smooth(minus_dm)
    sm_tr = wilder_smooth(trs)

    # --- Step 3: +DI, -DI, DX -----------------------------------------------
    dx_series: list[float] = []
    plus_di_latest = 0.0
    minus_di_latest = 0.0
    for p, m, t in zip(sm_plus, sm_minus, sm_tr, strict=True):
        if t <= 0:
            plus_di = 0.0
            minus_di = 0.0
        else:
            plus_di = 100.0 * (p / t)
            minus_di = 100.0 * (m / t)
        denom = plus_di + minus_di
        dx = 100.0 * abs(plus_di - minus_di) / denom if denom > 0 else 0.0
        dx_series.append(dx)
        plus_di_latest = plus_di
        minus_di_latest = minus_di

    # --- Step 4: ADX = Wilder-smooth DX over `period` ----------------------
    if len(dx_series) < period:
        return None
    adx = sum(dx_series[:period]) / period
    for dx in dx_series[period:]:
        adx = (adx * (period - 1) + dx) / period

    return {
        "adx": round(adx, 3),
        "plus_di": round(plus_di_latest, 3),
        "minus_di": round(minus_di_latest, 3),
    }


# ---------------------------------------------------------------------------
# ADX regime classification
# ---------------------------------------------------------------------------


def classify_adx_regime(adx: float | None) -> str:
    """Map an ADX value to a regime label.

    Thresholds follow the Wilder convention widely used in trading research:
        adx > 25  → trending   (momentum / breakout strategies preferred)
        adx < 20  → ranging    (mean-reversion preferred)
        20-25     → transition (reduce confidence in either style)
        None      → unknown    (insufficient data)
    """
    if adx is None:
        return "unknown"
    if adx >= 25.0:
        return "trending"
    if adx < 20.0:
        return "ranging"
    return "transition"
