"""Tranche 6 Lane 9 wiring — Lane 4 (source quality) ↔ Lane 7 (SEC + earnings).

The source-quality registry exposes a canonical list of sources the
daemon scores. Lane 7 (SEC EDGAR + earnings calls) added two new
source names; we register them here and assert the wiring with a small
suite of cases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from lib.source_quality.registry import (
    BUILTIN_SOURCES,
    SourceQualityEntry,
    default_registry,
    records_for_sources,
    register_source,
    registered_sources,
    source_signal_to_record,
)

# ---------------------------------------------------------------------------
# Case 1 — SEC EDGAR + earnings calls are registered out of the box.
# ---------------------------------------------------------------------------


def test_sec_and_earnings_are_registered_by_default() -> None:
    """Built-in registry must include sec_edgar + earnings_calls."""
    names = registered_sources()
    assert "sec_edgar" in names
    assert "earnings_calls" in names


def test_tdr_pro_is_registered_by_default() -> None:
    """Built-in registry must include tdr_pro (DeFi Report Pro podcast)."""
    names = registered_sources()
    assert "tdr_pro" in names


def test_builtin_sources_have_72h_lookahead_for_filings() -> None:
    """Filings have a slower half-life → 72h lookahead, not the 24h default."""
    by_name = {e.name: e for e in BUILTIN_SOURCES}
    assert by_name["sec_edgar"].lookahead_hours == 72
    assert by_name["earnings_calls"].lookahead_hours == 72


def test_tdr_pro_has_weekly_lookahead() -> None:
    """Macro research podcast uses a 7-day (168h) lookahead."""
    by_name = {e.name: e for e in BUILTIN_SOURCES}
    assert by_name["tdr_pro"].lookahead_hours == 168


# ---------------------------------------------------------------------------
# Case 2 — register_source is idempotent.
# ---------------------------------------------------------------------------


def test_register_source_is_idempotent() -> None:
    """Registering the same entry twice yields the same final state."""
    entry = SourceQualityEntry(
        name="sec_edgar-idempotence-probe",
        lookahead_hours=72,
        description="probe",
        tags=("sec",),
    )
    register_source(entry)
    first = default_registry()[entry.name]
    register_source(entry)
    second = default_registry()[entry.name]
    assert first == second
    # Cleanup
    from lib.source_quality.registry import _REGISTRY  # noqa: PLC0415

    _REGISTRY.pop(entry.name, None)


# ---------------------------------------------------------------------------
# Case 3 — third-party adapter can register a brand-new source.
# ---------------------------------------------------------------------------


def test_register_source_adds_a_new_name() -> None:
    """Adapters can register sources beyond the built-ins."""
    name = "tranche-9-test-source-do-not-ship"
    entry = SourceQualityEntry(
        name=name,
        lookahead_hours=12,
        description="local test only",
        tags=("test",),
    )
    register_source(entry)
    try:
        names = registered_sources()
        assert name in names
        assert default_registry()[name].lookahead_hours == 12
    finally:
        # Clean up to keep the process-local registry honest for other tests.
        from lib.source_quality.registry import _REGISTRY  # noqa: PLC0415

        _REGISTRY.pop(name, None)


# ---------------------------------------------------------------------------
# Case 4 — source_signal_to_record bridges Lane 7 ↔ Lane 4.
# ---------------------------------------------------------------------------


def test_source_signal_to_record_preserves_fields() -> None:
    """A SourceSignal-shaped object converts to a SignalRecord losslessly."""
    fake_signal = SimpleNamespace(
        source="sec_edgar",
        symbol="AAPL",
        direction="bear",
        confidence=0.7,
        timestamp_iso="2026-04-29T13:00:00+00:00",
    )
    rec = source_signal_to_record(fake_signal)
    assert rec.source == "sec_edgar"
    assert rec.symbol == "AAPL"
    assert rec.direction == "bear"
    assert rec.confidence == 0.7
    assert rec.timestamp == datetime(2026, 4, 29, 13, 0, tzinfo=UTC)


def test_records_for_sources_filters_by_name() -> None:
    """Filtering by source name keeps only the requested set."""
    fakes = [
        SimpleNamespace(
            source="sec_edgar",
            symbol="AAPL",
            direction="bull",
            confidence=0.5,
            timestamp_iso="2026-04-29T12:00:00+00:00",
        ),
        SimpleNamespace(
            source="earnings_calls",
            symbol="MSFT",
            direction="bear",
            confidence=0.6,
            timestamp_iso="2026-04-29T13:00:00+00:00",
        ),
        SimpleNamespace(
            source="tradingview",
            symbol="BTC",
            direction="bull",
            confidence=0.9,
            timestamp_iso="2026-04-29T14:00:00+00:00",
        ),
    ]
    only_sec = records_for_sources(fakes, only={"sec_edgar"})
    assert len(only_sec) == 1
    assert only_sec[0].source == "sec_edgar"

    only_lane7 = records_for_sources(fakes, only={"sec_edgar", "earnings_calls"})
    assert {r.source for r in only_lane7} == {"sec_edgar", "earnings_calls"}
