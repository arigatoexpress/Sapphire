"""Deflated Sharpe Ratio (DSR) — vendored from lib/analytics/deflated_sharpe.py.

The dashboard image is self-contained (only services/analytics_dashboard/ is
copied into the container), so we vendor this small stdlib-only routine here
rather than reaching into lib/analytics. Keep this in sync with the upstream
module if its formula changes (last sync: 2026-05-02, after PR #554).

References:
    Bailey, D.H., López de Prado, M. (2014). "The Deflated Sharpe Ratio".
    Journal of Portfolio Management, 40(5), 94-107.
"""

from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def expected_max_sharpe(sharpe_list: list[float]) -> float:
    """Asymptotic expectation of the maximum of N IID Sharpe ratios."""
    n = len(sharpe_list)
    if n <= 1:
        return sharpe_list[0] if sharpe_list else 0.0
    euler_mascheroni = 0.5772156649
    gbr = (1 - euler_mascheroni) * _norm_cdf(1 / math.sqrt(n)) + euler_mascheroni * _norm_cdf(
        math.sqrt(2 / max(1, n - 1))
    )
    return math.sqrt(2) * math.sqrt(max(0.0, -2 * math.log(max(1e-12, gbr))))


def deflated_sharpe(
    sharpe_list: list[float],
    selected_sharpe: float | None = None,
    *,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    n_obs: int = 252,
) -> dict:
    """Compute deflated Sharpe ratio + probability for a set of trial Sharpes."""
    if not sharpe_list:
        return {"sharpe": 0.0, "deflated_sharpe": 0.0, "probability": 0.0, "trials": 0}

    sr = selected_sharpe if selected_sharpe is not None else max(sharpe_list)
    sr_star = expected_max_sharpe(sharpe_list)

    correction_inner = (1 - skewness * sr + ((kurtosis - 1) / 4) * sr**2) / max(1, n_obs)
    correction = math.sqrt(max(0.0, correction_inner))
    deflated = (sr - sr_star) / max(1e-9, correction)
    prob = _norm_cdf(deflated)

    return {
        "sharpe": round(sr, 4),
        "deflated_sharpe": round(deflated, 4),
        "probability": round(prob, 4),
        "trials": len(sharpe_list),
    }


def annualized_sharpe(returns: list[float], periods_per_year: int = 252) -> float:
    """Annualized Sharpe assuming zero risk-free rate."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(periods_per_year)
