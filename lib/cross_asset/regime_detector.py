"""Deterministic regime detection from cross-asset correlations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from lib.cross_asset.correlation_matrix import MethodMatrix

REGIME_LABELS: tuple[str, ...] = (
    "risk_on_correlated",
    "risk_on_decorrelated",
    "risk_off_flight_to_dollar",
    "crisis_correlation_spike",
    "regime_uncertain",
)

RISK_ASSETS = frozenset({"BTC", "ETH", "SOL", "SPY", "QQQ"})
DOLLAR_ASSETS = frozenset({"DXY", "USD", "JPY", "CNY"})
DEFENSIVE_ASSETS = frozenset({"XAUUSD", "GOLD", "GLD", "VIX"})


@dataclass(frozen=True)
class RegimeLabel:
    """Point-in-time market regime label."""

    timestamp: str
    label: str
    confidence: float
    drivers: list[str]
    metrics: dict[str, float | int | None]
    previous_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).replace(microsecond=0).isoformat()


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _coerce_matrix(
    raw: MethodMatrix | Mapping[str, Any],
) -> tuple[list[str], list[list[float | None]], str]:
    if isinstance(raw, MethodMatrix):
        return raw.assets, raw.matrix, raw.window
    assets = [str(asset).upper() for asset in raw.get("assets", [])]  # type: ignore[union-attr]
    matrix = raw.get("matrix", [])  # type: ignore[union-attr]
    window = str(raw.get("window", "unknown"))  # type: ignore[union-attr]
    return assets, matrix, window


def _pair_values(
    assets: list[str],
    matrix: list[list[float | None]],
    *,
    left_filter: Iterable[str] | None = None,
    right_filter: Iterable[str] | None = None,
    cross_only: bool = False,
) -> list[float]:
    left_set = {item.upper() for item in left_filter or assets}
    right_set = {item.upper() for item in right_filter or assets}
    same_filter = left_set == right_set
    values: list[float] = []
    for i, left in enumerate(assets):
        for j, right in enumerate(assets):
            if j <= i:
                continue
            left_u = left.upper()
            right_u = right.upper()
            if same_filter:
                include = left_u in left_set and right_u in left_set
            else:
                include = (left_u in left_set and right_u in right_set) or (
                    right_u in left_set and left_u in right_set
                )
            if not include:
                continue
            if cross_only and (
                (left_u in left_set and right_u in left_set)
                or (left_u in right_set and right_u in right_set)
            ):
                continue
            try:
                value = matrix[i][j]
            except (IndexError, TypeError):
                continue
            if isinstance(value, int | float):
                values.append(float(value))
    return values


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _avg_abs(values: list[float]) -> float | None:
    return sum(abs(value) for value in values) / len(values) if values else None


def detect_regime(
    correlation_matrix: MethodMatrix | Mapping[str, Any] | None,
    *,
    timestamp: datetime | str | None = None,
    previous_label: str | None = None,
) -> RegimeLabel:
    """Label the market regime using deterministic matrix heuristics."""
    ts = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp or _now_iso())
    if correlation_matrix is None:
        return RegimeLabel(
            timestamp=ts,
            label="regime_uncertain",
            confidence=0.0,
            drivers=["matrix unavailable"],
            metrics={
                "risk_asset_correlation": None,
                "broad_abs_correlation": None,
                "risk_dollar_correlation": None,
                "observed_pairs": 0,
            },
            previous_label=previous_label,
        )

    assets, matrix, window = _coerce_matrix(correlation_matrix)
    risk_values = _pair_values(assets, matrix, left_filter=RISK_ASSETS, right_filter=RISK_ASSETS)
    broad_values = _pair_values(assets, matrix)
    risk_dollar_values = _pair_values(
        assets,
        matrix,
        left_filter=RISK_ASSETS,
        right_filter=DOLLAR_ASSETS,
        cross_only=True,
    )
    risk_defensive_values = _pair_values(
        assets,
        matrix,
        left_filter=RISK_ASSETS,
        right_filter=DEFENSIVE_ASSETS,
        cross_only=True,
    )

    risk_corr = _avg(risk_values)
    broad_abs = _avg_abs(broad_values)
    dollar_corr = _avg(risk_dollar_values)
    defensive_corr = _avg(risk_defensive_values)
    observed_pairs = len(broad_values)
    drivers = [f"window={window}", f"observed_pairs={observed_pairs}"]

    if observed_pairs < 3 or risk_corr is None:
        label = "regime_uncertain"
        confidence = 0.2 if observed_pairs else 0.0
        drivers.append("insufficient pair coverage")
    elif (broad_abs or 0.0) >= 0.72 or (risk_corr >= 0.72 and abs(dollar_corr or 0.0) >= 0.42):
        label = "crisis_correlation_spike"
        confidence = min(0.96, 0.62 + max(broad_abs or 0.0, risk_corr) * 0.34)
        drivers.append("broad absolute correlation spike")
    elif (dollar_corr or 0.0) <= -0.35 and risk_corr >= 0.30:
        label = "risk_off_flight_to_dollar"
        confidence = min(0.94, 0.55 + abs(dollar_corr or 0.0) * 0.35 + risk_corr * 0.10)
        drivers.append("risk assets moving against dollar bloc")
    elif risk_corr >= 0.55 and (dollar_corr is None or dollar_corr > -0.25):
        label = "risk_on_correlated"
        confidence = min(0.92, 0.50 + risk_corr * 0.42)
        drivers.append("risk assets positively correlated")
    elif 0.05 <= risk_corr < 0.55 and abs(dollar_corr or 0.0) < 0.35 and (broad_abs or 0.0) < 0.60:
        label = "risk_on_decorrelated"
        confidence = min(0.86, 0.45 + (0.55 - risk_corr) * 0.45)
        drivers.append("risk assets positive but dispersed")
    else:
        label = "regime_uncertain"
        confidence = 0.35
        drivers.append("mixed cross-asset evidence")

    if previous_label and previous_label != label:
        drivers.append(f"transition_from={previous_label}")

    return RegimeLabel(
        timestamp=ts,
        label=label,
        confidence=round(confidence, 4),
        drivers=drivers,
        metrics={
            "risk_asset_correlation": _round(risk_corr),
            "broad_abs_correlation": _round(broad_abs),
            "risk_dollar_correlation": _round(dollar_corr),
            "risk_defensive_correlation": _round(defensive_corr),
            "observed_pairs": observed_pairs,
        },
        previous_label=previous_label,
    )


def label_regime_history(
    matrices: Iterable[MethodMatrix | Mapping[str, Any] | None],
    *,
    timestamps: Iterable[datetime | str] | None = None,
    min_persistence: int = 2,
) -> list[RegimeLabel]:
    """Label a matrix sequence and smooth one-sample transition flicker."""
    ts_values = list(timestamps or [])
    raw_labels: list[RegimeLabel] = []
    previous: str | None = None
    for idx, matrix in enumerate(matrices):
        ts = ts_values[idx] if idx < len(ts_values) else None
        label = detect_regime(matrix, timestamp=ts, previous_label=previous)
        raw_labels.append(label)
        previous = label.label

    if min_persistence <= 1 or len(raw_labels) < 3:
        return raw_labels

    smoothed: list[RegimeLabel] = []
    idx = 0
    while idx < len(raw_labels):
        label = raw_labels[idx].label
        run_end = idx + 1
        while run_end < len(raw_labels) and raw_labels[run_end].label == label:
            run_end += 1
        run_len = run_end - idx
        replacement = smoothed[-1].label if smoothed and run_len < min_persistence else label
        for item in raw_labels[idx:run_end]:
            if replacement == item.label:
                smoothed.append(item)
            else:
                drivers = list(item.drivers) + [f"smoothed_from={item.label}"]
                smoothed.append(
                    RegimeLabel(
                        timestamp=item.timestamp,
                        label=replacement,
                        confidence=round(min(item.confidence, 0.55), 4),
                        drivers=drivers,
                        metrics=dict(item.metrics),
                        previous_label=item.previous_label,
                    )
                )
        idx = run_end
    return smoothed


__all__ = [
    "DEFENSIVE_ASSETS",
    "DOLLAR_ASSETS",
    "REGIME_LABELS",
    "RISK_ASSETS",
    "RegimeLabel",
    "detect_regime",
    "label_regime_history",
]
