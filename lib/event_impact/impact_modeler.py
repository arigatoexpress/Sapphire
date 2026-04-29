"""Empirical reaction-window model for curated historical events."""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .event_corpus import HistoricalEvent

DEFAULT_HORIZONS_HOURS: tuple[int, ...] = (1, 6, 24, 168)
MODEL_SCHEMA_VERSION = "0.1.0"


@dataclass(frozen=True)
class PriceBar:
    """Minimal OHLCV point used by the impact modeler."""

    timestamp: datetime
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PriceBar:
        ts_raw = raw.get("timestamp") or raw.get("ts") or raw.get("date")
        if ts_raw is None:
            raise ValueError("bar missing timestamp")
        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return cls(
            timestamp=ts.astimezone(UTC),
            close=float(raw.get("close")),
            open=_float_or_none(raw.get("open")),
            high=_float_or_none(raw.get("high")),
            low=_float_or_none(raw.get("low")),
            volume=_float_or_none(raw.get("volume")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.astimezone(UTC).replace(microsecond=0).isoformat()
        return payload


@dataclass(frozen=True)
class ImpactProfile:
    """Fitted reaction profile for one event type, asset, and horizon."""

    category: str
    sub_category: str
    asset: str
    horizon_hours: int
    mean_return_pct: float
    median_return_pct: float
    n: int
    stdev: float
    confidence_interval_95: tuple[float, float]
    direction_consensus: float
    sample_event_ids: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence_interval_95"] = list(self.confidence_interval_95)
        payload["sample_event_ids"] = list(self.sample_event_ids)
        payload["notes"] = list(self.notes)
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ImpactProfile:
        return cls(
            category=str(raw["category"]),
            sub_category=str(raw["sub_category"]),
            asset=str(raw["asset"]).upper(),
            horizon_hours=int(raw["horizon_hours"]),
            mean_return_pct=float(raw["mean_return_pct"]),
            median_return_pct=float(raw["median_return_pct"]),
            n=int(raw["n"]),
            stdev=float(raw["stdev"]),
            confidence_interval_95=(
                float(raw["confidence_interval_95"][0]),
                float(raw["confidence_interval_95"][1]),
            ),
            direction_consensus=float(raw["direction_consensus"]),
            sample_event_ids=tuple(raw.get("sample_event_ids") or ()),
            notes=tuple(raw.get("notes") or ()),
        )


@dataclass(frozen=True)
class ImpactModel:
    """Collection of impact profiles plus model metadata."""

    profiles: tuple[ImpactProfile, ...]
    generated_at: str
    horizons_hours: tuple[int, ...] = DEFAULT_HORIZONS_HOURS
    schema_version: str = MODEL_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "horizons_hours": list(self.horizons_hours),
            "profiles": [profile.to_dict() for profile in self.profiles],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ImpactModel:
        return cls(
            schema_version=str(raw.get("schema_version") or MODEL_SCHEMA_VERSION),
            generated_at=str(raw.get("generated_at") or ""),
            horizons_hours=tuple(int(v) for v in raw.get("horizons_hours", DEFAULT_HORIZONS_HOURS)),
            profiles=tuple(ImpactProfile.from_dict(p) for p in raw.get("profiles", [])),
            metadata=dict(raw.get("metadata") or {}),
        )

    def profile_map(self) -> dict[tuple[str, str, str, int], ImpactProfile]:
        return {
            (p.category, p.sub_category, p.asset.upper(), p.horizon_hours): p for p in self.profiles
        }


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_bars(raw_bars: list[PriceBar | dict[str, Any]]) -> list[PriceBar]:
    bars: list[PriceBar] = []
    for bar in raw_bars:
        bars.append(bar if isinstance(bar, PriceBar) else PriceBar.from_dict(bar))
    return sorted(bars, key=lambda b: b.timestamp)


def _bar_at_or_after(bars: list[PriceBar], timestamp: datetime) -> PriceBar | None:
    target = timestamp.astimezone(UTC)
    for bar in bars:
        if bar.timestamp >= target:
            return bar
    return None


def _reaction_pct(event: HistoricalEvent, bars: list[PriceBar], horizon_hours: int) -> float | None:
    start = _bar_at_or_after(bars, event.timestamp)
    end = _bar_at_or_after(bars, event.timestamp + timedelta(hours=horizon_hours))
    if start is None or end is None or start.close <= 0:
        return None
    return (end.close - start.close) / start.close * 100.0


def _profile(
    *,
    category: str,
    sub_category: str,
    asset: str,
    horizon_hours: int,
    samples: list[tuple[HistoricalEvent, float]],
    min_sample_for_tight_band: int,
) -> ImpactProfile:
    returns = [value for _, value in samples]
    n = len(returns)
    mean = statistics.fmean(returns) if returns else 0.0
    median = statistics.median(returns) if returns else 0.0
    stdev = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    if n <= 1:
        half_width = 25.0
        notes = ("single_or_zero_sample_wide_band",)
    else:
        half_width = 1.96 * stdev / math.sqrt(n)
        notes = ()
    if n < min_sample_for_tight_band:
        half_width = max(half_width, 12.0)
        notes = (*notes, "small_sample_wide_band")
    positives = sum(1 for r in returns if r > 0)
    negatives = sum(1 for r in returns if r < 0)
    direction_consensus = (positives - negatives) / n if n else 0.0
    return ImpactProfile(
        category=category,
        sub_category=sub_category,
        asset=asset.upper(),
        horizon_hours=int(horizon_hours),
        mean_return_pct=round(mean, 6),
        median_return_pct=round(median, 6),
        n=n,
        stdev=round(stdev, 6),
        confidence_interval_95=(round(mean - half_width, 6), round(mean + half_width, 6)),
        direction_consensus=round(direction_consensus, 6),
        sample_event_ids=tuple(e.event_id for e, _ in samples),
        notes=notes,
    )


def build_impact_model(
    events: list[HistoricalEvent],
    bars_by_asset: dict[str, list[PriceBar | dict[str, Any]]],
    *,
    horizons_hours: tuple[int, ...] = DEFAULT_HORIZONS_HOURS,
    generated_at: datetime | None = None,
    min_sample_for_tight_band: int = 5,
) -> ImpactModel:
    """Fit reaction profiles by exact sub-category and category fallback.

    The model includes both specific profiles and a synthetic ``sub_category='*'``
    fallback per category. Lookup code chooses the specific profile first.
    """
    normalized = {asset.upper(): normalize_bars(bars) for asset, bars in bars_by_asset.items()}
    buckets: dict[tuple[str, str, str, int], list[tuple[HistoricalEvent, float]]] = {}
    for event in events:
        for asset in event.assets:
            bars = normalized.get(asset.upper())
            if not bars:
                continue
            for horizon in horizons_hours:
                pct = _reaction_pct(event, bars, horizon)
                if pct is None:
                    continue
                exact = (event.category, event.sub_category, asset.upper(), int(horizon))
                general = (event.category, "*", asset.upper(), int(horizon))
                buckets.setdefault(exact, []).append((event, pct))
                buckets.setdefault(general, []).append((event, pct))

    profiles = [
        _profile(
            category=category,
            sub_category=sub_category,
            asset=asset,
            horizon_hours=horizon,
            samples=samples,
            min_sample_for_tight_band=min_sample_for_tight_band,
        )
        for (category, sub_category, asset, horizon), samples in sorted(buckets.items())
    ]
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    return ImpactModel(
        profiles=tuple(profiles),
        generated_at=generated.isoformat(),
        horizons_hours=tuple(int(h) for h in horizons_hours),
        metadata={
            "events_seen": len(events),
            "assets_seen": sorted(normalized),
            "methodology": "close-to-close event reaction windows",
            "small_sample_policy": f"n<{min_sample_for_tight_band} forces wide confidence bands",
        },
    )
