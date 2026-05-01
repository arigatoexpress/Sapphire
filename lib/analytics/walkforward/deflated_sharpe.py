"""Walk-forward-aware wrapper around ``lib.analytics.deflated_sharpe``.

The Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) corrects for
multiple-testing bias when comparing strategies on the same backtest data.
The base implementation in ``lib.analytics.deflated_sharpe`` accepts:

    sharpe_list: list[float]   — one annualised Sharpe per evaluated strategy
    selected_sharpe: float     — Sharpe of the chosen strategy (default: max)
    skewness, kurtosis, n_obs  — distributional parameters of the trial returns
    threshold                  — pass/fail probability cutoff (default 0.95)

For walk-forward, the relevant input is *not* the per-trial Sharpe of the
naïve full-data sweep but rather the per-window OOS Sharpes from a
``WalkforwardResult`` (or any equivalent sequence). This wrapper:

1. Accepts a ``WalkforwardResult`` (or a plain list of per-window Sharpes plus
   a chosen-window Sharpe) and produces the right inputs to
   ``deflated_sharpe_ratio``.
2. Computes ``n_obs`` from the concatenated test-period bar count rather than
   the raw bar count of the full backtest, so the multiple-testing penalty is
   calibrated against the actual OOS sample, not the in-sample artifact.
3. Computes skewness and excess kurtosis from the concatenated test returns
   (deterministic stdlib estimator) so ``deflated_sharpe_ratio`` gets honest
   non-Gaussian moments rather than the default Gaussian assumption.
4. Returns a ``WalkforwardDSRResult`` augmenting the base ``DSRResult`` with
   the walk-forward-specific provenance (n_windows, window_sharpes, n_obs_oos).

CRITICAL: this module **does not modify** ``lib/analytics/deflated_sharpe.py``.
It only imports the public ``deflated_sharpe_ratio`` and ``DSRResult`` symbols
and wraps their behaviour for the walk-forward case.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from lib.analytics.deflated_sharpe import DSRResult, deflated_sharpe_ratio

__all__ = [
    "WalkforwardDSRResult",
    "deflated_sharpe_for_walkforward",
]


# ---------------------------------------------------------------------------
# Pure stdlib moment estimators
# ---------------------------------------------------------------------------


def _mean(xs: Sequence[float]) -> float:
    n = len(xs)
    return sum(xs) / n if n else 0.0


def _moment(xs: Sequence[float], order: int) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** order for x in xs) / n


def sample_skewness(xs: Sequence[float]) -> float:
    """Biased population skewness — same convention as scipy.stats.skew(bias=True)."""
    n = len(xs)
    if n < 2:
        return 0.0
    m2 = _moment(xs, 2)
    m3 = _moment(xs, 3)
    if m2 <= 0:
        return 0.0
    return m3 / (m2**1.5)


def sample_kurtosis(xs: Sequence[float]) -> float:
    """Pearson kurtosis (= excess + 3). Returns 3.0 for a normal distribution."""
    n = len(xs)
    if n < 2:
        return 3.0
    m2 = _moment(xs, 2)
    m4 = _moment(xs, 4)
    if m2 <= 0:
        return 3.0
    return m4 / (m2**2)


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass
class WalkforwardDSRResult:
    """Walk-forward-aware DSR with full provenance of the inputs we built."""

    base: DSRResult
    n_windows: int
    n_obs_oos: int
    window_sharpes: list[float] = field(default_factory=list)
    skewness: float = 0.0
    kurtosis: float = 0.0
    selected_sharpe: float = 0.0
    threshold: float = 0.95
    note: str = ""

    @property
    def passed(self) -> bool:
        return self.base.passed

    @property
    def probability(self) -> float:
        return self.base.probability

    @property
    def deflated_sharpe(self) -> float:
        return self.base.deflated_sharpe

    @property
    def trials(self) -> int:
        return self.base.trials

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.base.passed,
            "probability": self.base.probability,
            "sharpe": self.base.sharpe,
            "deflated_sharpe": self.base.deflated_sharpe,
            "trials": self.base.trials,
            "n_windows": self.n_windows,
            "n_obs_oos": self.n_obs_oos,
            "window_sharpes": list(self.window_sharpes),
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "selected_sharpe": self.selected_sharpe,
            "threshold": self.threshold,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def _coerce_sharpes(window_sharpes: Iterable[float]) -> list[float]:
    out: list[float] = []
    for v in window_sharpes:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def deflated_sharpe_for_walkforward(
    walkforward_result: Any | None = None,
    *,
    window_sharpes: Sequence[float] | None = None,
    test_returns: Sequence[float] | None = None,
    selected_sharpe: float | None = None,
    threshold: float = 0.95,
    n_obs_override: int | None = None,
) -> WalkforwardDSRResult:
    """Compute the Deflated Sharpe Ratio over a walk-forward run.

    Either pass a ``WalkforwardResult`` instance (preferred — provenance is
    carried) or supply ``window_sharpes`` + ``test_returns`` directly. The
    selected Sharpe defaults to the maximum among the window Sharpes; pass
    ``selected_sharpe`` to override.

    The degrees-of-freedom (``n_obs``) used inside
    ``deflated_sharpe_ratio`` is derived from the concatenated OOS test-return
    sample, not from the in-sample bar count. This correctly penalises a
    walk-forward that ran many short test windows vs. one with fewer / longer
    windows. Override via ``n_obs_override`` if you need to mirror a
    publication's convention.

    Args:
        walkforward_result: Optional ``WalkforwardResult``. If provided, its
                            ``windows[*].test_sharpe`` and
                            ``concatenated_test_returns`` populate the inputs.
        window_sharpes:     Per-window Sharpe sequence (used iff
                            ``walkforward_result`` is None or has no windows).
        test_returns:       Concatenated OOS bar returns (used iff
                            ``walkforward_result`` is None).
        selected_sharpe:    Override the chosen-strategy Sharpe.
        threshold:          DSR pass threshold (default 0.95).
        n_obs_override:     Force a specific n_obs (advanced).

    Returns:
        ``WalkforwardDSRResult``.
    """
    sharpes: list[float] = []
    rets: list[float] = []
    n_windows = 0
    note = ""

    if walkforward_result is not None and getattr(walkforward_result, "windows", None):
        sharpes = _coerce_sharpes(w.test_sharpe for w in walkforward_result.windows)
        rets = list(getattr(walkforward_result, "concatenated_test_returns", []) or [])
        n_windows = len(walkforward_result.windows)
        note = f"from WalkforwardResult({walkforward_result.strategy_cls}, {walkforward_result.symbol})"

    if not sharpes and window_sharpes is not None:
        sharpes = _coerce_sharpes(window_sharpes)
        n_windows = len(sharpes)
        if not note:
            note = "from explicit window_sharpes"
    if not rets and test_returns is not None:
        rets = list(test_returns)

    if not sharpes:
        # Fall back to a degenerate single-trial Sharpe so ``deflated_sharpe_ratio``
        # never sees an empty list. The DSR will collapse to a trivial computation
        # but the wrapper still returns a structured result rather than raising.
        sharpes = [0.0]
        note = note or "no window sharpes — degenerate DSR"

    if selected_sharpe is None:
        selected_sharpe = max(sharpes)

    n_obs = n_obs_override if n_obs_override is not None else max(2, len(rets))

    skewness = sample_skewness(rets) if rets else 0.0
    kurtosis = sample_kurtosis(rets) if rets else 3.0

    base = deflated_sharpe_ratio(
        sharpes,
        selected_sharpe=selected_sharpe,
        skewness=skewness,
        kurtosis=kurtosis,
        n_obs=n_obs,
        threshold=threshold,
    )

    return WalkforwardDSRResult(
        base=base,
        n_windows=n_windows,
        n_obs_oos=len(rets),
        window_sharpes=sharpes,
        skewness=round(skewness, 6),
        kurtosis=round(kurtosis, 6),
        selected_sharpe=float(selected_sharpe),
        threshold=float(threshold),
        note=note,
    )


# ---------------------------------------------------------------------------
# Re-export DSRResult for convenience
# ---------------------------------------------------------------------------

__all__.append("DSRResult")
