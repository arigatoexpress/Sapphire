"""Historical event-impact modeling for Sapphire intelligence surfaces."""

from .audit import (
    AUDIT_SCHEMA_VERSION,
    AccuracyAuditReport,
    AuditObservation,
    audit_expected_reactions,
    audit_from_files,
    realized_return_pct,
)
from .event_corpus import (
    DEFAULT_CORPUS_PATH,
    EVENT_SCHEMA_VERSION,
    HistoricalEvent,
    dedupe_events,
    load_events,
    validate_event,
)
from .impact_modeler import (
    DEFAULT_HORIZONS_HOURS,
    ImpactModel,
    ImpactProfile,
    PriceBar,
    build_impact_model,
)
from .lookup import ExpectedReaction, MacroEvent, lookup

__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "AccuracyAuditReport",
    "AuditObservation",
    "DEFAULT_CORPUS_PATH",
    "DEFAULT_HORIZONS_HOURS",
    "EVENT_SCHEMA_VERSION",
    "ExpectedReaction",
    "HistoricalEvent",
    "ImpactModel",
    "ImpactProfile",
    "MacroEvent",
    "PriceBar",
    "audit_expected_reactions",
    "audit_from_files",
    "build_impact_model",
    "dedupe_events",
    "load_events",
    "lookup",
    "realized_return_pct",
    "validate_event",
]
