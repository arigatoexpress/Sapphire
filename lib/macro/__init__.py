"""Regulatory and macro intelligence primitives for Sapphire."""

from __future__ import annotations

from lib.macro.calendar import CalendarEvent, MacroCalendar, build_calendar
from lib.macro.classifier import MacroClassification, classify_event, enrich_event
from lib.macro.sources import (
    MAX_EVENTS_PER_PULL,
    MAX_FORWARD_CALENDAR_DAYS,
    MAX_PULLS_PER_HOUR_PER_SOURCE,
    BISRSSSource,
    BLSEmploymentRSSSource,
    CFTCRSSSource,
    ECBRSSSource,
    FedRSSSource,
    FOMCCalendarSource,
    MacroEvent,
    SECAtomSource,
    TreasuryAuctionsSource,
    build_default_sources,
)

__all__ = [
    "BISRSSSource",
    "BLSEmploymentRSSSource",
    "CFTCRSSSource",
    "CalendarEvent",
    "ECBRSSSource",
    "FOMCCalendarSource",
    "FedRSSSource",
    "MAX_EVENTS_PER_PULL",
    "MAX_FORWARD_CALENDAR_DAYS",
    "MAX_PULLS_PER_HOUR_PER_SOURCE",
    "MacroCalendar",
    "MacroClassification",
    "MacroEvent",
    "SECAtomSource",
    "TreasuryAuctionsSource",
    "build_calendar",
    "build_default_sources",
    "classify_event",
    "enrich_event",
]
