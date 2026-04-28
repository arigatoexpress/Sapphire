"""Curated historical event corpus for event-impact modeling.

The corpus is intentionally plain JSONL so it can be reviewed in diffs,
expanded by humans, and consumed by tools without a database. Every row
must include a citation URL in ``metadata.source_url``; modeled claims
without citation are rejected at load time.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVENT_SCHEMA_VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_PATH = REPO_ROOT / "data" / "event_corpus" / "events.jsonl"

REQUIRED_CATEGORIES = {
    "fomc_decision",
    "etf_approval",
    "exchange_hack",
    "regulatory_enforcement",
    "macro_shock",
}


@dataclass(frozen=True)
class HistoricalEvent:
    """One timestamped historical event with citation metadata."""

    event_id: str
    timestamp: datetime
    category: str
    sub_category: str
    title: str
    assets: tuple[str, ...]
    magnitude: float | None = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> HistoricalEvent:
        validate_event(raw)
        ts_raw = str(raw["timestamp"]).replace("Z", "+00:00")
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return cls(
            event_id=str(raw["event_id"]),
            timestamp=ts.astimezone(UTC),
            category=str(raw["category"]),
            sub_category=str(raw["sub_category"]),
            title=str(raw["title"]),
            assets=tuple(str(a).upper() for a in raw["assets"]),
            magnitude=_maybe_float(raw.get("magnitude")),
            notes=str(raw.get("notes") or ""),
            metadata=dict(raw.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.astimezone(UTC).replace(microsecond=0).isoformat()
        payload["assets"] = list(self.assets)
        payload["schema_version"] = EVENT_SCHEMA_VERSION
        return payload


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_event(raw: dict[str, Any]) -> None:
    """Raise ``ValueError`` when a corpus row is not model-safe."""
    required = {
        "event_id",
        "timestamp",
        "category",
        "sub_category",
        "title",
        "assets",
        "metadata",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError(f"event missing required fields: {', '.join(missing)}")
    if str(raw["category"]) not in REQUIRED_CATEGORIES:
        raise ValueError(f"unsupported category: {raw['category']!r}")
    if not isinstance(raw["assets"], list) or not raw["assets"]:
        raise ValueError("event assets must be a non-empty list")
    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("event metadata must be a dict")
    source_url = str(metadata.get("source_url") or "")
    if not source_url.startswith(("https://", "http://")):
        raise ValueError("event metadata.source_url must be an HTTP URL")
    try:
        datetime.fromisoformat(str(raw["timestamp"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"event timestamp is not ISO-8601: {raw['timestamp']!r}") from exc


def dedupe_events(events: list[HistoricalEvent]) -> list[HistoricalEvent]:
    """Deduplicate by stable event id, keeping the first occurrence."""
    seen: set[str] = set()
    out: list[HistoricalEvent] = []
    for event in events:
        key = event.event_id.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(event)
    return sorted(out, key=lambda e: (e.timestamp, e.event_id))


def load_events(path: Path | str = DEFAULT_CORPUS_PATH) -> list[HistoricalEvent]:
    """Load and validate a JSONL event corpus."""
    corpus_path = Path(path)
    events: list[HistoricalEvent] = []
    for lineno, raw_line in enumerate(corpus_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{corpus_path}:{lineno}: invalid JSON: {exc}") from exc
        try:
            events.append(HistoricalEvent.from_dict(raw))
        except ValueError as exc:
            raise ValueError(f"{corpus_path}:{lineno}: {exc}") from exc
    return dedupe_events(events)


def events_by_category(events: list[HistoricalEvent]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event.category] = counts.get(event.category, 0) + 1
    return counts
