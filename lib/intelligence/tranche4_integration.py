"""Pure wiring helpers for the Tranche 4 intelligence surfaces.

This module intentionally contains no live collectors and no trading actions.
It only normalizes already-produced lane artifacts into the context shapes that
other Sapphire services can consume.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.event_impact.lookup import lookup

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1

TRANCHE4_FEED_TOPICS: dict[str, tuple[str, ...]] = {
    "narrative_synthesis": ("narrative.thesis.generated",),
    "cross_asset": ("regime.shift.detected", "correlation.breakdown"),
    "macro_intel": ("macro.event.detected", "macro.calendar.window_opening"),
    "onchain_intel": ("onchain.snapshot.updated",),
    "event_impact": ("event.expected_reaction.published",),
    "counterparty_intel": ("counterparty.smart_money.move",),
}

TRANCHE4_EVENT_TOPICS: tuple[str, ...] = tuple(
    topic for topics in TRANCHE4_FEED_TOPICS.values() for topic in topics
)


@dataclass(frozen=True)
class _FeedArtifactSpec:
    feed: str
    topics: tuple[str, ...]
    patterns: tuple[str, ...]


_FEED_ARTIFACTS: tuple[_FeedArtifactSpec, ...] = (
    _FeedArtifactSpec(
        "narrative_synthesis",
        TRANCHE4_FEED_TOPICS["narrative_synthesis"],
        ("data/narratives/*/theses.jsonl",),
    ),
    _FeedArtifactSpec(
        "cross_asset",
        TRANCHE4_FEED_TOPICS["cross_asset"],
        ("data/cross_asset/*/regimes.jsonl", "data/cross_asset/*/breakdowns.jsonl"),
    ),
    _FeedArtifactSpec(
        "macro_intel",
        TRANCHE4_FEED_TOPICS["macro_intel"],
        ("data/macro/*/events.jsonl", "data/macro/*/calendar.jsonl"),
    ),
    _FeedArtifactSpec(
        "onchain_intel",
        TRANCHE4_FEED_TOPICS["onchain_intel"],
        ("data/intelligence/latest/onchain_intel.json", "data/onchain_intel/*.json"),
    ),
    _FeedArtifactSpec(
        "event_impact",
        TRANCHE4_FEED_TOPICS["event_impact"],
        ("data/event_impact/model_*.json", "data/event_impact/expected_reactions.jsonl"),
    ),
    _FeedArtifactSpec(
        "counterparty_intel",
        TRANCHE4_FEED_TOPICS["counterparty_intel"],
        ("data/counterparty/*/counterparty_signals.json",),
    ),
)


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0).isoformat()


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        maybe = value.to_dict()
        return dict(maybe) if isinstance(maybe, Mapping) else {}
    return {}


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:
        return default
    return out


def _symbol(signal: Mapping[str, Any]) -> str:
    return str(signal.get("symbol") or signal.get("asset") or "").strip().upper()


def _extract_regime(cross_asset: Any) -> dict[str, Any] | None:
    payload = _coerce_mapping(cross_asset)
    regime = _coerce_mapping(payload.get("regime")) or payload
    label = regime.get("label") or regime.get("regime_label")
    if not label:
        return None
    return {
        "label": str(label),
        "confidence": _coerce_float(regime.get("confidence"), default=0.0),
        "generated_at": regime.get("timestamp") or regime.get("generated_at"),
        "source": "cross_asset",
    }


def _extract_macro_event(signal: Mapping[str, Any], macro_calendar: Any) -> dict[str, Any] | None:
    target = _symbol(signal)
    payload = _coerce_mapping(macro_calendar)
    rows: Iterable[Any]
    if isinstance(macro_calendar, list):
        rows = macro_calendar
    else:
        rows = (
            payload.get("events") or payload.get("calendar_window") or payload.get("upcoming") or []
        )
    candidates: list[dict[str, Any]] = []
    for raw in rows:
        row = _coerce_mapping(raw)
        if not row:
            continue
        assets = {
            str(a).upper() for a in row.get("assets") or row.get("assets_likely_affected") or []
        }
        if target and assets and target not in assets:
            continue
        candidates.append(row)
    if not candidates:
        return None
    candidates.sort(key=lambda row: str(row.get("scheduled_at") or row.get("published_at") or ""))
    event = candidates[0]
    return {
        "title": str(event.get("title") or ""),
        "category": str(event.get("category") or ""),
        "scheduled_at": event.get("scheduled_at") or event.get("published_at"),
        "source": event.get("source"),
        "source_url": event.get("source_url") or event.get("url"),
        "assets": list(event.get("assets") or event.get("assets_likely_affected") or []),
    }


def _onchain_regime_from_heat(heat: float) -> str:
    if heat >= 75.0:
        return "euphoria"
    if heat >= 50.0:
        return "accumulation"
    if heat <= 25.0:
        return "capitulation"
    return "distribution"


def _extract_onchain(signal: Mapping[str, Any], onchain: Any) -> dict[str, Any] | None:
    target = _symbol(signal)
    payload = _coerce_mapping(onchain)
    if not payload:
        return None
    if payload.get("regime"):
        return {
            "asset": target or payload.get("asset"),
            "regime": str(payload.get("regime")),
            "heat_score": _coerce_float(payload.get("heat_score"), default=0.0),
            "source": "onchain_intel",
        }
    assets = _coerce_mapping(payload.get("assets"))
    asset_row = _coerce_mapping(assets.get(target)) if target else {}
    composite = _coerce_mapping(asset_row.get("composite"))
    heat = _coerce_float(composite.get("onchain_heat_score"), default=0.0)
    if not asset_row and heat == 0.0:
        return None
    return {
        "asset": target,
        "regime": _onchain_regime_from_heat(heat),
        "heat_score": heat,
        "input_count": int(_coerce_float(composite.get("input_count"), default=0.0)),
        "source": "onchain_intel",
    }


def _extract_counterparty(signal: Mapping[str, Any], counterparty: Any) -> dict[str, Any] | None:
    target = _symbol(signal)
    payload = _coerce_mapping(counterparty)
    signals = payload.get("signals") if payload else None
    rows = (
        signals
        if isinstance(signals, list)
        else counterparty
        if isinstance(counterparty, list)
        else []
    )
    best: dict[str, Any] | None = None
    for raw in rows:
        row = _coerce_mapping(raw)
        if target and str(row.get("asset") or "").upper() != target:
            continue
        if best is None or abs(_coerce_float(row.get("smart_money_consensus"))) > abs(
            _coerce_float(best.get("smart_money_consensus"))
        ):
            best = row
    if best is None and payload.get("smart_money_consensus") is not None:
        best = payload
    if best is None:
        return None
    return {
        "asset": str(best.get("asset") or target),
        "side": str(best.get("side") or ""),
        "smart_money_consensus": _coerce_float(best.get("smart_money_consensus")),
        "traders_corroborating": int(_coerce_float(best.get("traders_corroborating"), default=0.0)),
        "generated_at": best.get("generated_at"),
        "source": "counterparty_intel",
    }


def _extract_expected_reaction(expected_reaction: Any) -> dict[str, Any] | None:
    payload = _coerce_mapping(expected_reaction)
    if not payload:
        return None
    if hasattr(expected_reaction, "to_dict"):
        payload = expected_reaction.to_dict()
    return {
        "asset": payload.get("asset"),
        "horizon_hours": payload.get("horizon_hours"),
        "mean_return_pct": payload.get("mean_return_pct"),
        "confidence_interval_95": payload.get("confidence_interval_95"),
        "direction_consensus": payload.get("direction_consensus"),
        "confidence": payload.get("confidence"),
        "matched_level": payload.get("matched_level"),
        "source": "event_impact",
    }


def build_narrative_context(
    signal: Mapping[str, Any],
    *,
    cross_asset: Any = None,
    macro_calendar: Any = None,
    onchain: Any = None,
    counterparty: Any = None,
    expected_reaction: Any = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Normalize Tranche 4 lane outputs into one narrative prompt block."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(generated_at),
        "symbol": _symbol(signal),
        "cross_asset_regime": _extract_regime(cross_asset),
        "next_macro_event": _extract_macro_event(signal, macro_calendar),
        "onchain_regime": _extract_onchain(signal, onchain),
        "smart_money_consensus": _extract_counterparty(signal, counterparty),
        "expected_reaction": _extract_expected_reaction(expected_reaction),
    }


def enrich_signal_for_narrative(
    signal: Mapping[str, Any],
    *,
    context: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a copy of ``signal`` carrying Tranche 4 narrative context."""
    out = dict(signal)
    if context is not None:
        out["tranche4_context"] = dict(context)
    else:
        out.setdefault(
            "tranche4_context",
            build_narrative_context(out, generated_at=generated_at),
        )
    return out


def expected_reaction_events(
    macro_event: Mapping[str, Any] | Any,
    *,
    model: Mapping[str, Any] | Any,
    assets: Sequence[str] = ("BTC", "ETH", "SOL"),
    horizons: Sequence[int] = (6, 24),
    generated_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build event-bus payloads for ``event.expected_reaction.published``."""
    rows: list[dict[str, Any]] = []
    for asset in assets:
        for horizon in horizons:
            reaction = lookup(macro_event, asset, int(horizon), model=model)
            row = {
                "schema_version": SCHEMA_VERSION,
                "event_type": "event.expected_reaction.published",
                "generated_at": _now_iso(generated_at),
                "macro_event": _coerce_mapping(macro_event),
                "expected_reaction": reaction.to_dict(),
                "source": "event_impact",
            }
            rows.append(row)
    return rows


def _iter_json_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if path.suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
        return rows
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        for key in ("signals", "events", "calendar", "profiles"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [parsed]
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    return []


def _latest_timestamp(
    rows: Sequence[dict[str, Any]], fallback: datetime | None = None
) -> str | None:
    keys = (
        "generated_at",
        "timestamp",
        "timestamp_iso",
        "published_at",
        "scheduled_at",
        "detected_at",
    )
    values: list[str] = []
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value:
                values.append(str(value))
                break
        thesis = row.get("thesis")
        if isinstance(thesis, dict) and thesis.get("generated_at"):
            values.append(str(thesis["generated_at"]))
    if values:
        return sorted(values)[-1]
    return fallback.astimezone(UTC).replace(microsecond=0).isoformat() if fallback else None


def feed_status_from_artifacts(
    *,
    root: str | Path = REPO_ROOT,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Summarize Tranche 4 feed artifacts for the observability dashboard."""
    base = Path(root)
    feeds: list[dict[str, Any]] = []
    total_events = 0
    with_events = 0
    for spec in _FEED_ARTIFACTS:
        files: list[Path] = []
        for pattern in spec.patterns:
            files.extend(sorted(base.glob(pattern)))
        rows: list[dict[str, Any]] = []
        latest_fallback: datetime | None = None
        for path in files:
            rows.extend(_iter_json_rows(path))
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                mtime = None
            if mtime and (latest_fallback is None or mtime > latest_fallback):
                latest_fallback = mtime
        event_count = len(rows)
        total_events += event_count
        if event_count:
            with_events += 1
        relative_paths = [
            str(path.relative_to(base)) if path.is_relative_to(base) else str(path)
            for path in files[-5:]
        ]
        feeds.append(
            {
                "feed": spec.feed,
                "topics": list(spec.topics),
                "status": "pass" if event_count else "warn",
                "artifacts_seen": len(files),
                "events_seen": event_count,
                "last_event_at": _latest_timestamp(rows, fallback=latest_fallback),
                "relative_paths": relative_paths,
                "mode": "read_only_artifact_summary",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "read_only_tranche4_feed_status",
        "generated_at": _now_iso(generated_at),
        "status": "pass" if with_events == len(_FEED_ARTIFACTS) else "warn",
        "totals": {
            "feeds": len(_FEED_ARTIFACTS),
            "with_events": with_events,
            "events_seen": total_events,
        },
        "feeds": feeds,
    }


__all__ = [
    "TRANCHE4_EVENT_TOPICS",
    "TRANCHE4_FEED_TOPICS",
    "build_narrative_context",
    "enrich_signal_for_narrative",
    "expected_reaction_events",
    "feed_status_from_artifacts",
]
