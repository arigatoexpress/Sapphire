"""Deterministic lead/lag correlation analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Any

from lib.cross_asset.correlation_matrix import align_pair, coerce_close_series, pearson


@dataclass(frozen=True)
class LeadLagResult:
    pair: tuple[str, str]
    best_lag: int
    correlation: float | None
    interpretation: str
    scores: dict[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def lead_lag_for_pair(
    left_asset: str,
    right_asset: str,
    left_series: Any,
    right_series: Any,
    *,
    max_lag: int = 6,
    min_observations: int = 12,
) -> LeadLagResult:
    """Return the lag with the strongest absolute Pearson correlation.

    Positive lags mean ``left_asset`` leads ``right_asset`` by that many
    observations. Negative lags mean ``right_asset`` leads.
    """
    timestamps, left_values, right_values = align_pair(
        coerce_close_series(left_series),
        coerce_close_series(right_series),
    )
    del timestamps
    scores: dict[str, float | None] = {}
    best_lag = 0
    best_value: float | None = None
    for lag in range(-max_lag, max_lag + 1):
        if lag > 0:
            xs = left_values[:-lag]
            ys = right_values[lag:]
        elif lag < 0:
            xs = left_values[-lag:]
            ys = right_values[:lag]
        else:
            xs = left_values
            ys = right_values
        value = pearson(xs, ys) if len(xs) >= min_observations else None
        rounded = round(value, 4) if value is not None else None
        scores[str(lag)] = rounded
        if value is None:
            continue
        if best_value is None or abs(value) > abs(best_value):
            best_lag = lag
            best_value = value
    if best_value is None:
        interpretation = "insufficient overlap"
    elif best_lag > 0:
        interpretation = f"{left_asset} leads {right_asset} by {best_lag} observations"
    elif best_lag < 0:
        interpretation = f"{right_asset} leads {left_asset} by {abs(best_lag)} observations"
    else:
        interpretation = "contemporaneous"
    return LeadLagResult(
        pair=(left_asset, right_asset),
        best_lag=best_lag,
        correlation=round(best_value, 4) if best_value is not None else None,
        interpretation=interpretation,
        scores=scores,
    )


def analyze_lead_lag(
    series_by_asset: Mapping[str, Any],
    *,
    max_lag: int = 6,
    min_observations: int = 12,
    limit: int = 20,
) -> list[LeadLagResult]:
    assets = sorted(str(asset).upper() for asset in series_by_asset)
    results = [
        lead_lag_for_pair(
            left,
            right,
            series_by_asset[left],
            series_by_asset[right],
            max_lag=max_lag,
            min_observations=min_observations,
        )
        for left, right in combinations(assets, 2)
    ]
    return sorted(
        results,
        key=lambda item: abs(item.correlation or 0.0),
        reverse=True,
    )[:limit]


__all__ = ["LeadLagResult", "analyze_lead_lag", "lead_lag_for_pair"]
