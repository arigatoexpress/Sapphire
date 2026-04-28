"""Forward-looking macro calendar utilities."""

from __future__ import annotations

import calendar as py_calendar
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from lib.macro.classifier import classify_event
from lib.macro.sources import BLS_EMPSIT_RSS_URL, MacroEvent

MAX_FORWARD_CALENDAR_DAYS = 90
BLS_EMPSIT_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    category: str
    scheduled_at: datetime
    source: str
    source_url: str
    assets: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "scheduled_at": self.scheduled_at.astimezone(UTC).isoformat(),
            "source": self.source,
            "source_url": self.source_url,
            "assets": list(self.assets),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CalendarEvent:
        scheduled_raw = str(payload.get("scheduled_at") or "")
        scheduled = datetime.fromisoformat(scheduled_raw)
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)
        return cls(
            id=str(payload.get("id") or ""),
            title=str(payload.get("title") or ""),
            category=str(payload.get("category") or "other"),
            scheduled_at=scheduled.astimezone(UTC),
            source=str(payload.get("source") or ""),
            source_url=str(payload.get("source_url") or ""),
            assets=tuple(str(v) for v in payload.get("assets") or ()),
            metadata=dict(payload.get("metadata") or {}),
        )


def _calendar_id(title: str, scheduled_at: datetime, source: str) -> str:
    material = f"{source}|{title}|{scheduled_at.astimezone(UTC).isoformat()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def event_to_calendar(event: MacroEvent) -> CalendarEvent | None:
    kind = str(event.metadata.get("event_kind") or "")
    if event.source not in {"fed_fomc", "treasury_auctions"} and not kind.startswith("scheduled"):
        return None
    classification = classify_event(event)
    source_url = str(event.metadata.get("source_url") or event.url)
    return CalendarEvent(
        id=_calendar_id(event.title, event.published_at, event.source),
        title=event.title,
        category=classification.category,
        scheduled_at=event.published_at,
        source=event.source,
        source_url=source_url,
        assets=classification.assets_likely_affected,
        metadata={
            **event.metadata,
            "macro_event_id": event.id,
            "classification": classification.to_dict(),
        },
    )


def first_friday(year: int, month: int) -> date:
    cal = py_calendar.Calendar(firstweekday=py_calendar.MONDAY)
    for day in cal.itermonthdates(year, month):
        if day.month == month and day.weekday() == py_calendar.FRIDAY:
            return day
    raise ValueError(f"no Friday found for {year}-{month:02d}")


def payroll_calendar_events(
    *,
    now: datetime | None = None,
    days: int = MAX_FORWARD_CALENDAR_DAYS,
) -> list[CalendarEvent]:
    """Generate BLS Employment Situation placeholders for the forward window.

    The first-Friday rule is an approximation for planning. The runbook marks
    these as confirmation-only until the official BLS schedule page is parsed
    or manually reviewed.
    """

    anchor = (now or datetime.now(UTC)).astimezone(UTC)
    end = anchor + timedelta(days=max(1, min(days, MAX_FORWARD_CALENDAR_DAYS)))
    month_cursor = date(anchor.year, anchor.month, 1)
    events: list[CalendarEvent] = []
    while month_cursor <= end.date().replace(day=1) + timedelta(days=32):
        release_date = first_friday(month_cursor.year, month_cursor.month)
        scheduled = datetime.combine(release_date, time(hour=12, minute=30), tzinfo=UTC)
        if anchor <= scheduled <= end:
            title = f"BLS Employment Situation release: {release_date:%B %Y}"
            events.append(
                CalendarEvent(
                    id=_calendar_id(title, scheduled, "bls_empsit_schedule"),
                    title=title,
                    category="data_release",
                    scheduled_at=scheduled,
                    source="bls_empsit_schedule",
                    source_url=BLS_EMPSIT_SCHEDULE_URL,
                    assets=("equities", "USD", "gold", "BTC"),
                    metadata={
                        "source_name": "BLS Employment Situation schedule",
                        "source_url": BLS_EMPSIT_SCHEDULE_URL,
                        "feed_url": BLS_EMPSIT_RSS_URL,
                        "official_source": True,
                        "event_kind": "scheduled_data_release",
                        "approximation": "first_friday_0830_et",
                    },
                )
            )
        if month_cursor.month == 12:
            month_cursor = date(month_cursor.year + 1, 1, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month + 1, 1)
    return events


class MacroCalendar:
    def __init__(self, events: Iterable[CalendarEvent] = ()) -> None:
        dedup: dict[str, CalendarEvent] = {}
        for event in events:
            dedup[event.id] = event
        self.events = tuple(sorted(dedup.values(), key=lambda item: item.scheduled_at))

    def upcoming(
        self,
        *,
        now: datetime | None = None,
        hours: float = 24.0,
        asset: str | None = None,
    ) -> list[CalendarEvent]:
        anchor = (now or datetime.now(UTC)).astimezone(UTC)
        end = anchor + timedelta(hours=max(0.0, float(hours)))
        asset_norm = asset.upper() if asset else None
        rows: list[CalendarEvent] = []
        for event in self.events:
            when = event.scheduled_at.astimezone(UTC)
            if when < anchor or when > end:
                continue
            if asset_norm and asset_norm not in {a.upper() for a in event.assets}:
                continue
            rows.append(event)
        return rows

    def next_event_for_asset(
        self,
        asset: str,
        *,
        now: datetime | None = None,
    ) -> CalendarEvent | None:
        asset_norm = asset.upper()
        anchor = (now or datetime.now(UTC)).astimezone(UTC)
        for event in self.events:
            if event.scheduled_at.astimezone(UTC) < anchor:
                continue
            if asset_norm in {a.upper() for a in event.assets}:
                return event
        return None

    def in_next_hours(self, hours: float, *, now: datetime | None = None) -> list[CalendarEvent]:
        return self.upcoming(now=now, hours=hours)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]


def build_calendar(
    macro_events: Sequence[MacroEvent] = (),
    *,
    now: datetime | None = None,
    include_static: bool = True,
    max_forward_days: int = MAX_FORWARD_CALENDAR_DAYS,
) -> MacroCalendar:
    anchor = (now or datetime.now(UTC)).astimezone(UTC)
    horizon = anchor + timedelta(days=max(1, min(max_forward_days, MAX_FORWARD_CALENDAR_DAYS)))
    events: list[CalendarEvent] = []
    for event in macro_events:
        cal_event = event_to_calendar(event)
        if cal_event is None:
            continue
        when = cal_event.scheduled_at.astimezone(UTC)
        if anchor <= when <= horizon:
            events.append(cal_event)
    if include_static:
        events.extend(payroll_calendar_events(now=anchor, days=max_forward_days))
    return MacroCalendar(events)


def calendar_from_dicts(rows: Iterable[dict[str, Any]]) -> MacroCalendar:
    return MacroCalendar(CalendarEvent.from_dict(row) for row in rows)


__all__ = [
    "BLS_EMPSIT_SCHEDULE_URL",
    "CalendarEvent",
    "MAX_FORWARD_CALENDAR_DAYS",
    "MacroCalendar",
    "build_calendar",
    "calendar_from_dicts",
    "event_to_calendar",
    "first_friday",
    "payroll_calendar_events",
]
