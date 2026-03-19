from __future__ import annotations

from datetime import date
from typing import Iterable

from bis.models import ProgressSignal
from bis.models import PropensityScore
from bis.models import PropertyAsset


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _years_between(start: date, end: date) -> float:
    return max(0.0, (end - start).days / 365.0)


def _lease_term_component(item: PropertyAsset, today: date) -> float:
    if not item.lease_expiration:
        return 0.35
    remaining_years = _years_between(today, item.lease_expiration)
    return _clamp((8.0 - remaining_years) / 8.0)


def _rent_gap_component(item: PropertyAsset) -> float:
    if item.current_rent_psf is None or item.submarket_avg_rent_psf is None:
        return 0.25
    baseline = max(0.01, item.submarket_avg_rent_psf)
    delta = abs(item.submarket_avg_rent_psf - item.current_rent_psf)
    return _clamp(delta / baseline)


def _ownership_duration_component(item: PropertyAsset, today: date) -> float:
    if not item.ownership_start:
        return 0.3
    held_years = _years_between(item.ownership_start, today)
    return _clamp(held_years / 15.0)


def _signal_component(item: PropertyAsset, signals: Iterable[ProgressSignal]) -> float:
    matched = [signal for signal in signals if signal.property_urn == item.property_urn]
    if not matched:
        return 0.0
    # Recent signals imply a higher probability of transaction movement.
    impact_sum = 0.0
    for signal in matched:
        if signal.value_delta is not None and signal.value_delta > 0:
            impact_sum += min(2.0, signal.value_delta / 50000.0)
        else:
            impact_sum += 0.6
    return _clamp(impact_sum / 6.0)


def compute_propensity_score(
    item: PropertyAsset,
    signals: Iterable[ProgressSignal],
    *,
    today: date | None = None,
) -> PropensityScore:
    today = today or date.today()

    lease_component = _lease_term_component(item, today)
    rent_component = _rent_gap_component(item)
    ownership_component = _ownership_duration_component(item, today)
    eps_component = _signal_component(item, signals)

    weights = {
        "lease_term": 0.38,
        "rent_gap": 0.23,
        "ownership_duration": 0.27,
        "eps": 0.12,
    }

    score = 100.0 * (
        lease_component * weights["lease_term"]
        + rent_component * weights["rent_gap"]
        + ownership_component * weights["ownership_duration"]
        + eps_component * weights["eps"]
    )
    if item.redo:
        score = max(0.0, score - 8.0)

    return PropensityScore(
        property_urn=item.property_urn,
        score=round(score, 2),
        components={
            "lease_term": round(lease_component, 3),
            "rent_gap": round(rent_component, 3),
            "ownership_duration": round(ownership_component, 3),
            "eps": round(eps_component, 3),
        },
    )
