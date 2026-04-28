"""Lookup expected market reactions for new macro or news events."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .impact_modeler import ImpactModel, ImpactProfile


@dataclass(frozen=True)
class MacroEvent:
    """Small compatibility shape for Lane 3 macro events."""

    title: str
    category: str
    sub_category: str = "*"
    timestamp: datetime | None = None
    assets_likely_affected: tuple[str, ...] = ()
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_any(cls, raw: MacroEvent | dict[str, Any] | Any) -> MacroEvent:
        if isinstance(raw, MacroEvent):
            return raw
        if not isinstance(raw, dict):
            raw = {
                "title": getattr(raw, "title", ""),
                "category": getattr(raw, "category", ""),
                "sub_category": getattr(raw, "sub_category", "*"),
                "timestamp": getattr(raw, "timestamp", None),
                "assets_likely_affected": getattr(raw, "assets_likely_affected", ()),
                "source_url": getattr(raw, "source_url", None),
                "metadata": getattr(raw, "metadata", {}),
            }
        ts = _coerce_datetime(raw.get("timestamp"))
        sub_category = raw.get("sub_category") or raw.get("subcategory") or "*"
        assets = raw.get("assets_likely_affected") or raw.get("assets") or ()
        return cls(
            title=str(raw.get("title") or ""),
            category=str(raw.get("category") or ""),
            sub_category=str(sub_category or "*"),
            timestamp=ts,
            assets_likely_affected=tuple(str(a).upper() for a in assets),
            source_url=raw.get("source_url"),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ExpectedReaction:
    """Returned lookup result with an honesty-first fallback marker."""

    asset: str
    horizon_hours: int
    category: str
    sub_category: str
    mean_return_pct: float
    median_return_pct: float
    confidence_interval_95: tuple[float, float]
    direction_consensus: float
    n: int
    confidence: str
    matched_level: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence_interval_95"] = list(self.confidence_interval_95)
        payload["notes"] = list(self.notes)
        return payload


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def load_model(path: Path | str) -> ImpactModel:
    return ImpactModel.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _reaction_from_profile(profile: ImpactProfile, matched_level: str) -> ExpectedReaction:
    if profile.n >= 20:
        confidence = "medium"
    elif profile.n >= 5:
        confidence = "low"
    else:
        confidence = "very_low"
    return ExpectedReaction(
        asset=profile.asset,
        horizon_hours=profile.horizon_hours,
        category=profile.category,
        sub_category=profile.sub_category,
        mean_return_pct=profile.mean_return_pct,
        median_return_pct=profile.median_return_pct,
        confidence_interval_95=profile.confidence_interval_95,
        direction_consensus=profile.direction_consensus,
        n=profile.n,
        confidence=confidence,
        matched_level=matched_level,
        notes=tuple(profile.notes),
    )


def lookup(
    event: MacroEvent | dict[str, Any] | Any,
    asset: str,
    horizon_hours: int,
    *,
    model: ImpactModel | dict[str, Any],
) -> ExpectedReaction:
    """Return the best available expected reaction for ``event``.

    Fallback order is exact category/sub-category, category wildcard, and
    then an explicit no-data wide-band response.
    """
    macro_event = MacroEvent.from_any(event)
    model_obj = ImpactModel.from_dict(model) if isinstance(model, dict) else model
    asset_key = str(asset).upper()
    horizon = int(horizon_hours)
    profiles = model_obj.profile_map()
    exact_key = (macro_event.category, macro_event.sub_category, asset_key, horizon)
    if macro_event.sub_category != "*" and exact_key in profiles:
        return _reaction_from_profile(profiles[exact_key], "exact")
    general_key = (macro_event.category, "*", asset_key, horizon)
    if general_key in profiles:
        return _reaction_from_profile(profiles[general_key], "category")
    return ExpectedReaction(
        asset=asset_key,
        horizon_hours=horizon,
        category=macro_event.category,
        sub_category=macro_event.sub_category,
        mean_return_pct=0.0,
        median_return_pct=0.0,
        confidence_interval_95=(-100.0, 100.0),
        direction_consensus=0.0,
        n=0,
        confidence="none",
        matched_level="no_data",
        notes=("no historical profile matched; use as context, not a trading signal",),
    )
