#!/usr/bin/env python3
"""Offline post-corpus audit helper for event-impact model snapshots.

This helper intentionally performs no network fetches. It compares a fitted
event-impact model against a held-out event file and local OHLCV bars, then
emits deterministic JSON that can be checked into an operator report or used
by tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.event_impact import (  # noqa: E402
    HistoricalEvent,
    ImpactModel,
    PriceBar,
    load_events,
    lookup,
)
from lib.event_impact.impact_modeler import normalize_bars  # noqa: E402
from lib.event_impact.lookup import load_model  # noqa: E402


@dataclass(frozen=True)
class AuditRow:
    """One event/asset/horizon comparison row."""

    event_id: str
    event_timestamp: str
    category: str
    sub_category: str
    asset: str
    horizon_hours: int
    matched_level: str
    confidence: str
    sample_size: int
    expected_mean_return_pct: float
    expected_direction_consensus: float
    expected_confidence_interval_95: tuple[float, float]
    actual_return_pct: float | None
    sign_scored: bool
    sign_correct: bool | None
    interval_scored: bool
    within_confidence_interval: bool | None
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["expected_confidence_interval_95"] = list(self.expected_confidence_interval_95)
        return payload


@dataclass(frozen=True)
class AuditReport:
    """Deterministic summary plus row-level comparisons."""

    model_generated_at: str
    audit_cutoff: str
    horizons_hours: tuple[int, ...]
    post_corpus_events: int
    skipped_pre_cutoff_events: int
    rows: tuple[AuditRow, ...]

    def to_dict(self) -> dict[str, Any]:
        actual_rows = [row for row in self.rows if row.actual_return_pct is not None]
        sign_rows = [row for row in self.rows if row.sign_scored]
        interval_rows = [row for row in self.rows if row.interval_scored]
        sign_correct = sum(1 for row in sign_rows if row.sign_correct)
        interval_hits = sum(1 for row in interval_rows if row.within_confidence_interval)
        absolute_errors = [
            abs(row.actual_return_pct - row.expected_mean_return_pct)
            for row in actual_rows
            if row.matched_level != "no_data" and row.actual_return_pct is not None
        ]
        summary = {
            "post_corpus_events": self.post_corpus_events,
            "skipped_pre_cutoff_events": self.skipped_pre_cutoff_events,
            "rows": len(self.rows),
            "rows_with_actuals": len(actual_rows),
            "sign_scored": len(sign_rows),
            "sign_correct": sign_correct,
            "sign_accuracy": round(sign_correct / len(sign_rows), 6) if sign_rows else None,
            "interval_scored": len(interval_rows),
            "interval_hits": interval_hits,
            "interval_hit_rate": round(interval_hits / len(interval_rows), 6)
            if interval_rows
            else None,
            "mean_absolute_error_pct": round(sum(absolute_errors) / len(absolute_errors), 6)
            if absolute_errors
            else None,
        }
        return {
            "ok": True,
            "model_generated_at": self.model_generated_at,
            "audit_cutoff": self.audit_cutoff,
            "horizons_hours": list(self.horizons_hours),
            "summary": summary,
            "rows": [row.to_dict() for row in self.rows],
        }


def _coerce_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        ts = value
    else:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _bar_at_or_after(bars: list[PriceBar], timestamp: datetime) -> PriceBar | None:
    target = timestamp.astimezone(UTC)
    for bar in bars:
        if bar.timestamp >= target:
            return bar
    return None


def realized_return_pct(
    event: HistoricalEvent,
    bars: list[PriceBar],
    horizon_hours: int,
) -> float | None:
    """Return close-to-close realized return for one event horizon."""
    start = _bar_at_or_after(bars, event.timestamp)
    end = _bar_at_or_after(bars, event.timestamp + timedelta(hours=int(horizon_hours)))
    if start is None or end is None or start.close <= 0:
        return None
    return round((end.close - start.close) / start.close * 100.0, 6)


def _event_payload(event: HistoricalEvent) -> dict[str, Any]:
    return {
        "title": event.title,
        "category": event.category,
        "sub_category": event.sub_category,
        "timestamp": event.timestamp.isoformat(),
        "assets": list(event.assets),
        "source_url": event.metadata.get("source_url"),
        "metadata": event.metadata,
    }


def _score_row(
    *,
    event: HistoricalEvent,
    asset: str,
    horizon_hours: int,
    model: ImpactModel,
    bars: list[PriceBar] | None,
) -> AuditRow:
    expected = lookup(_event_payload(event), asset, horizon_hours, model=model)
    actual = realized_return_pct(event, bars, horizon_hours) if bars else None
    interval = expected.confidence_interval_95
    interval_scored = actual is not None and expected.matched_level != "no_data"
    within_interval = (
        interval[0] <= actual <= interval[1]
        if actual is not None and interval_scored
        else None
    )
    sign_scored = (
        actual is not None
        and actual != 0
        and expected.direction_consensus != 0
        and expected.matched_level != "no_data"
    )
    sign_correct = None
    if sign_scored:
        sign_correct = (actual > 0 and expected.direction_consensus > 0) or (
            actual < 0 and expected.direction_consensus < 0
        )
    skip_reason = None
    if actual is None:
        skip_reason = "missing_price_window"
    elif expected.matched_level == "no_data":
        skip_reason = "no_model_profile"
    elif not sign_scored:
        skip_reason = "neutral_prediction_or_actual"
    return AuditRow(
        event_id=event.event_id,
        event_timestamp=event.timestamp.isoformat(),
        category=event.category,
        sub_category=event.sub_category,
        asset=asset.upper(),
        horizon_hours=int(horizon_hours),
        matched_level=expected.matched_level,
        confidence=expected.confidence,
        sample_size=expected.n,
        expected_mean_return_pct=expected.mean_return_pct,
        expected_direction_consensus=expected.direction_consensus,
        expected_confidence_interval_95=expected.confidence_interval_95,
        actual_return_pct=actual,
        sign_scored=sign_scored,
        sign_correct=sign_correct,
        interval_scored=interval_scored,
        within_confidence_interval=within_interval,
        skip_reason=skip_reason,
    )


def audit_post_corpus_events(
    *,
    model: ImpactModel,
    events: list[HistoricalEvent],
    bars_by_asset: dict[str, list[PriceBar | dict[str, Any]]],
    horizons_hours: tuple[int, ...] = (6, 24),
    after: datetime | str | None = None,
) -> AuditReport:
    """Compare post-cutoff events to model expectations using local bars only."""
    cutoff = _coerce_datetime(after or model.generated_at)
    normalized_bars = {
        asset.upper(): normalize_bars(bars)
        for asset, bars in sorted(bars_by_asset.items())
    }
    post_events = [
        event
        for event in sorted(events, key=lambda e: (e.timestamp, e.event_id))
        if event.timestamp > cutoff
    ]
    skipped_pre_cutoff = len(events) - len(post_events)
    rows: list[AuditRow] = []
    for event in post_events:
        for asset in sorted({a.upper() for a in event.assets}):
            bars = normalized_bars.get(asset)
            for horizon in sorted(int(h) for h in horizons_hours):
                rows.append(
                    _score_row(
                        event=event,
                        asset=asset,
                        horizon_hours=horizon,
                        model=model,
                        bars=bars,
                    )
                )
    return AuditReport(
        model_generated_at=model.generated_at,
        audit_cutoff=cutoff.isoformat(),
        horizons_hours=tuple(sorted(int(h) for h in horizons_hours)),
        post_corpus_events=len(post_events),
        skipped_pre_cutoff_events=skipped_pre_cutoff,
        rows=tuple(rows),
    )


def load_bars_json(path: Path | str) -> dict[str, list[PriceBar]]:
    """Load local OHLCV JSON as ``{"BTC": [{"timestamp": ..., "close": ...}]}``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("bars JSON must be an object keyed by asset")
    bars_by_asset: dict[str, list[PriceBar]] = {}
    for asset, rows in raw.items():
        if not isinstance(rows, list):
            raise ValueError(f"bars for {asset} must be a list")
        bars_by_asset[str(asset).upper()] = normalize_bars(rows)
    return bars_by_asset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True, help="event-impact model JSON")
    parser.add_argument("--events", type=Path, required=True, help="held-out event JSONL")
    parser.add_argument("--bars-json", type=Path, required=True, help="local OHLCV JSON by asset")
    parser.add_argument("--horizon", action="append", dest="horizons", type=int)
    parser.add_argument("--after", help="override audit cutoff ISO timestamp")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args(argv)

    model = load_model(args.model)
    events = load_events(args.events)
    report = audit_post_corpus_events(
        model=model,
        events=events,
        bars_by_asset=load_bars_json(args.bars_json),
        horizons_hours=tuple(args.horizons or (6, 24)),
        after=args.after,
    ).to_dict()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
