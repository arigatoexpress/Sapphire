"""Deflated Sharpe Ratio (DSR) — Bailey & López de Prado (2014).

Corrects for multiple-testing bias when comparing strategies on the same
backtest data.  Given a set of trial Sharpe ratios, it returns the probability
that the *selected* (best-looking) strategy beats a Sharpe of 0 after
accounting for selection bias and non-Gaussian returns.

References:
    Bailey, D.H., López de Prado, M. (2014).  "The Deflated Sharpe Ratio".
    *Journal of Portfolio Management*, 40(5), 94-107.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DSRResult:
    sharpe: float
    deflated_sharpe: float
    probability: float
    trials: int
    passed: bool

    def to_dict(self) -> dict:
        return {
            "sharpe": self.sharpe,
            "deflated_sharpe": self.deflated_sharpe,
            "probability": self.probability,
            "trials": self.trials,
            "passed": self.passed,
        }


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def expected_max_sharpe(sharpe_list: list[float]) -> float:
    """Asymptotic expectation of the maximum of N IID Sharpe ratios."""
    n = len(sharpe_list)
    if n <= 1:
        return sharpe_list[0] if sharpe_list else 0.0
    euler_mascheroni = 0.5772156649
    # Analytical approximation from BLP 2014
    gbr = (1 - euler_mascheroni) * _norm_cdf(1 / math.sqrt(n)) + euler_mascheroni * _norm_cdf(
        math.sqrt(2 / max(1, n - 1))
    )
    return math.sqrt(2) * math.sqrt(max(0, -2 * math.log(gbr)))


def deflated_sharpe_ratio(
    sharpe_list: list[float],
    selected_sharpe: float | None = None,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    n_obs: int = 252,
    threshold: float = 0.95,
) -> DSRResult:
    """Compute DSR for a set of trial Sharpes.

    Args:
        sharpe_list: Annualised Sharpe ratios of all evaluated strategies.
        selected_sharpe: The Sharpe of the chosen strategy (default: max).
        skewness: Return distribution skewness (default 0 = normal).
        kurtosis: Return distribution excess kurtosis (default 3 = normal).
        n_obs: Number of observations used to compute each Sharpe.
        threshold: Probability threshold to declare DSR "passed".
    """
    if len(sharpe_list) == 0:
        raise ValueError("sharpe_list must not be empty")

    sr = selected_sharpe if selected_sharpe is not None else max(sharpe_list)
    sr_star = expected_max_sharpe(sharpe_list)

    # Non-Gaussian correction factor (Ledoit-Wolf moments)
    correction = math.sqrt(
        (1 - skewness * sr + ((kurtosis - 1) / 4) * sr**2) / n_obs
    )
    deflated = (sr - sr_star) / max(1e-9, correction)
    prob = _norm_cdf(deflated)

    return DSRResult(
        sharpe=sr,
        deflated_sharpe=deflated,
        probability=round(prob, 4),
        trials=len(sharpe_list),
        passed=prob >= threshold,
    )
