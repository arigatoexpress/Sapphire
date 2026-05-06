"""Regulatory and macro intelligence primitives for Sapphire."""

from __future__ import annotations

from lib.macro.calendar import CalendarEvent, MacroCalendar, build_calendar
from lib.macro.classifier import MacroClassification, classify_event, enrich_event
from lib.macro.fred_loader import (
    DEFAULT_MARKET_REGIME_SERIES,
    FRED_SERIES_OBSERVATIONS_URL,
    FredLoader,
    FredLoaderError,
    FredObservation,
    FredSeriesSnapshot,
    build_fred_observations_url,
    canonical_observation_id,
    fred_observation_rows,
    macro_feature_row,
    parse_fred_observations,
)
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
    "DEFAULT_MARKET_REGIME_SERIES",
    "ECBRSSSource",
    "FOMCCalendarSource",
    "FRED_SERIES_OBSERVATIONS_URL",
    "FedRSSSource",
    "FredLoader",
    "FredLoaderError",
    "FredObservation",
    "FredSeriesSnapshot",
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
    "build_fred_observations_url",
    "canonical_observation_id",
    "classify_event",
    "enrich_event",
    "fred_observation_rows",
    "macro_feature_row",
    "parse_fred_observations",
]
