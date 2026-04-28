"""Offline accuracy audit helpers for event-impact profiles.

This module intentionally does not fetch data. Callers supply a historical event
set, OHLCV bars, and an already-built :class:`ImpactModel`. The audit compares
the expected reaction profile Sapphire would have returned with the realized
post-event return observed in the supplied bars.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .event_corpus import HistoricalEvent, load_events
from .impact_modeler import DEFAULT_HORIZONS_HOURS, ImpactModel, PriceBar, normalize_bars
from .lookup import ExpectedReaction, lookup

AUDIT_SCHEMA_VERSION = "0.1.0"


@dataclass(frozen=True)
class AuditObservation:
    """One expected-vs-realized comparison for a historical event."""

    event_id: str
    category: str
    sub_category: str
    asset: str
    horizon_hours: int
    expected_mean_return_pct: float
    expected_direction_consensus: float
    expected_n: int
    expected_confidence: str
    matched_level: str
    actual_return_pct: float | None
    scored: bool
    direction_match: bool | None
    absolute_error_pct: float | None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["notes"] = list(self.notes)
        return payload


@dataclass(frozen=True)
class AccuracyAuditReport:
    """Aggregate audit report with honesty-first caveats."""

    generated_at: str
    observations: tuple[AuditObservation, ...]
    schema_version: str = AUDIT_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        scored = [obs for obs in self.observations if obs.scored]
        correct = [obs for obs in scored if obs.direction_match]
        errors = [
            obs.absolute_error_pct
            for obs in scored
            if obs.absolute_error_pct is not None
        ]
        by_asset: dict[str, dict[str, int]] = {}
        by_category: dict[str, dict[str, int]] = {}
        by_matched_level: dict[str, int] = {}
        no_data = 0
        missing_actual = 0
        for obs in self.observations:
            by_matched_level[obs.matched_level] = by_matched_level.get(obs.matched_level, 0) + 1
            if obs.matched_level == "no_data":
                no_data += 1
            if obs.actual_return_pct is None:
                missing_actual += 1
            for bucket, key in ((by_asset, obs.asset), (by_category, obs.category)):
                entry = bucket.setdefault(key, {"observations": 0, "scored": 0, "correct": 0})
                entry["observations"] += 1
                entry["scored"] += int(obs.scored)
                entry["correct"] += int(bool(obs.direction_match))
        caveats = audit_caveats(
            total=len(self.observations),
            scored=len(scored),
            no_data=no_data,
            missing_actual=missing_actual,
        )
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "summary": {
                "observations": len(self.observations),
                "scored": len(scored),
                "direction_correct": len(correct),
                "direction_accuracy": round(len(correct) / len(scored), 6) if scored else None,
                "mean_absolute_error_pct": round(statistics.fmean(errors), 6) if errors else None,
                "median_absolute_error_pct": round(statistics.median(errors), 6) if errors else None,
                "no_data": no_data,
                "missing_actual": missing_actual,
                "by_asset": by_asset,
                "by_category": by_category,
                "by_matched_level": by_matched_level,
                "caveats": caveats,
            },
            "metadata": dict(self.metadata),
            "observations_detail": [obs.to_dict() for obs in self.observations],
        }


def _coerce_model(model: ImpactModel | Mapping[str, Any]) -> ImpactModel:
    return ImpactModel.from_dict(dict(model)) if isinstance(model, Mapping) else model


def load_model(path: Path | str) -> ImpactModel:
    return ImpactModel.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def load_bars_by_asset(path: Path | str) -> dict[str, list[PriceBar]]:
    """Load fixture OHLCV from JSON.

    Supported shapes:

    * ``{"BTC": [{"timestamp": ..., "close": ...}]}``
    * ``[{"asset": "BTC", "timestamp": ..., "close": ...}]``
    """

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {
            str(asset).upper(): normalize_bars(list(rows or []))
            for asset, rows in raw.items()
        }
    if isinstance(raw, list):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            asset = str(row.get("asset") or "").upper()
            if not asset:
                continue
            grouped.setdefault(asset, []).append(row)
        return {asset: normalize_bars(rows) for asset, rows in grouped.items()}
    raise ValueError("bars fixture must be an asset mapping or a list of asset-tagged rows")


def _bar_at_or_after(bars: Sequence[PriceBar], timestamp: datetime) -> PriceBar | None:
    target = timestamp.astimezone(UTC)
    for bar in bars:
        if bar.timestamp >= target:
            return bar
    return None


def realized_return_pct(
    event: HistoricalEvent,
    bars: Sequence[PriceBar | dict[str, Any]],
    horizon_hours: int,
) -> float | None:
    normalized = normalize_bars(list(bars))
    start = _bar_at_or_after(normalized, event.timestamp)
    end = _bar_at_or_after(normalized, event.timestamp + timedelta(hours=int(horizon_hours)))
    if start is None or end is None or start.close <= 0:
        return None
    return round((end.close - start.close) / start.close * 100.0, 6)


def _prediction_sign(expected: ExpectedReaction) -> int:
    if expected.direction_consensus > 0:
        return 1
    if expected.direction_consensus < 0:
        return -1
    if expected.mean_return_pct > 0:
        return 1
    if expected.mean_return_pct < 0:
        return -1
    return 0


def _actual_sign(actual_return_pct: float | None) -> int:
    if actual_return_pct is None:
        return 0
    if actual_return_pct > 0:
        return 1
    if actual_return_pct < 0:
        return -1
    return 0


def _assets_for_event(event: HistoricalEvent, assets: Sequence[str] | None) -> tuple[str, ...]:
    if assets:
        allowed = {str(asset).upper() for asset in assets}
        return tuple(asset for asset in event.assets if asset.upper() in allowed)
    return event.assets


def audit_expected_reactions(
    events: Iterable[HistoricalEvent],
    bars_by_asset: Mapping[str, Sequence[PriceBar | dict[str, Any]]],
    model: ImpactModel | Mapping[str, Any],
    *,
    horizons_hours: Sequence[int] = DEFAULT_HORIZONS_HOURS,
    assets: Sequence[str] | None = None,
    generated_at: datetime | None = None,
) -> AccuracyAuditReport:
    """Compare model lookup expectations with realized post-event returns."""

    model_obj = _coerce_model(model)
    normalized_bars = {
        str(asset).upper(): normalize_bars(list(bars))
        for asset, bars in bars_by_asset.items()
    }
    observations: list[AuditObservation] = []
    for event in events:
        for asset in _assets_for_event(event, assets):
            bars = normalized_bars.get(asset.upper())
            for horizon in horizons_hours:
                expected = lookup(
                    {
                        "title": event.title,
                        "category": event.category,
                        "sub_category": event.sub_category,
                        "timestamp": event.timestamp,
                        "assets": event.assets,
                        "source_url": event.metadata.get("source_url"),
                    },
                    asset,
                    int(horizon),
                    model=model_obj,
                )
                actual = realized_return_pct(event, bars or (), int(horizon))
                pred_sign = _prediction_sign(expected)
                actual_sign = _actual_sign(actual)
                scored = (
                    expected.matched_level != "no_data"
                    and actual is not None
                    and pred_sign != 0
                    and actual_sign != 0
                )
                notes = list(expected.notes)
                if expected.matched_level == "no_data":
                    notes.append("no_expected_profile")
                if actual is None:
                    notes.append("missing_post_event_bar")
                if pred_sign == 0:
                    notes.append("flat_expected_direction")
                if actual_sign == 0 and actual is not None:
                    notes.append("flat_realized_return")
                observations.append(
                    AuditObservation(
                        event_id=event.event_id,
                        category=event.category,
                        sub_category=event.sub_category,
                        asset=asset.upper(),
                        horizon_hours=int(horizon),
                        expected_mean_return_pct=expected.mean_return_pct,
                        expected_direction_consensus=expected.direction_consensus,
                        expected_n=expected.n,
                        expected_confidence=expected.confidence,
                        matched_level=expected.matched_level,
                        actual_return_pct=actual,
                        scored=scored,
                        direction_match=(pred_sign == actual_sign) if scored else None,
                        absolute_error_pct=(
                            round(abs(expected.mean_return_pct - actual), 6)
                            if actual is not None and expected.matched_level != "no_data"
                            else None
                        ),
                        notes=tuple(dict.fromkeys(notes)),
                    )
                )
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    return AccuracyAuditReport(
        generated_at=generated.isoformat(),
        observations=tuple(observations),
        metadata={
            "methodology": "offline expected-profile lookup vs supplied post-event OHLCV returns",
            "horizons_hours": [int(h) for h in horizons_hours],
            "assets_filter": [str(a).upper() for a in assets] if assets else None,
            "model_generated_at": model_obj.generated_at,
        },
    )


def audit_from_files(
    *,
    events_path: Path | str,
    bars_path: Path | str,
    model_path: Path | str,
    horizons_hours: Sequence[int] = DEFAULT_HORIZONS_HOURS,
    assets: Sequence[str] | None = None,
) -> AccuracyAuditReport:
    return audit_expected_reactions(
        load_events(events_path),
        load_bars_by_asset(bars_path),
        load_model(model_path),
        horizons_hours=horizons_hours,
        assets=assets,
    )


def audit_caveats(
    *,
    total: int,
    scored: int,
    no_data: int,
    missing_actual: int,
) -> list[str]:
    caveats: list[str] = []
    if total == 0:
        caveats.append("no_observations_supplied")
    if scored < 20:
        caveats.append("small_scored_sample_wide_intervals")
    if no_data:
        caveats.append("some_events_have_no_expected_profile")
    if missing_actual:
        caveats.append("some_events_missing_post_event_ohlcv")
    caveats.append("direction_accuracy_is_context_not_a_trading_signal")
    return caveats


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "AccuracyAuditReport",
    "AuditObservation",
    "audit_caveats",
    "audit_expected_reactions",
    "audit_from_files",
    "load_bars_by_asset",
    "load_model",
    "realized_return_pct",
]
