"""Tranche 6 Lane 9 wiring — Lane 4 (source quality) ↔ Lane 7 (SEC + earnings).

The source-quality SNR / correlation / decay layer is source-agnostic: it
operates on :class:`~lib.source_quality.snr.SignalRecord` instances with a
``source`` string. The Lane 7 SEC EDGAR + earnings call adapters emit
correlator :class:`~lib.correlator.sources.SourceSignal` instances; this
module bridges the two by:

1. Defining a canonical source-name registry — the names the source-quality
   daemon recognises and reports against.
2. Providing a thin :func:`source_signal_to_record` helper that converts a
   correlator ``SourceSignal`` into a source-quality ``SignalRecord``,
   preserving the source name and direction without mutation.
3. Allowing third-party adapters (Lane 7's ``sec_edgar`` + ``earnings_calls``
   today, future Tranche 7 adapters tomorrow) to register their canonical
   source name + the eventual lookahead window they expect to be scored
   against.

Side-effect-free: the registry is a process-local dict. The daemon at
``services/source_quality/run.py`` is the only thing that touches the
filesystem. Importing this module is a no-op beyond populating the default
registry entries.

This module is read-only with respect to ``lib/sources/``. We never import a
specific Lane 7 source here at module level — adapters register themselves
by calling :func:`register_source` on import (or the daemon does it on
their behalf when it spawns the daily report). That keeps the dependency
graph one-way.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from lib.source_quality.snr import (
    DEFAULT_OUTCOME_WINDOW_HOURS,
    SignalRecord,
)

__all__ = [
    "SourceQualityEntry",
    "default_registry",
    "register_source",
    "registered_sources",
    "source_signal_to_record",
    "BUILTIN_SOURCES",
]


@dataclass(frozen=True)
class SourceQualityEntry:
    """One source's source-quality registration."""

    name: str
    lookahead_hours: int = DEFAULT_OUTCOME_WINDOW_HOURS
    description: str = ""
    # Tags help the dashboard filter; e.g. {"sec", "filings"} for SEC EDGAR.
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lookahead_hours": self.lookahead_hours,
            "description": self.description,
            "tags": list(self.tags),
        }


# Built-in registrations. Tranche 6 Lane 7 added two new sources on top of
# the Tranche 5 + earlier signal feeds; we register them here so the
# source-quality daemon scores them on the next run.
BUILTIN_SOURCES: tuple[SourceQualityEntry, ...] = (
    SourceQualityEntry(
        name="tradingview",
        lookahead_hours=DEFAULT_OUTCOME_WINDOW_HOURS,
        description="TradingView webhook signals (Lane 0).",
        tags=("trading", "ta"),
    ),
    SourceQualityEntry(
        name="telegram_intel",
        lookahead_hours=DEFAULT_OUTCOME_WINDOW_HOURS,
        description="Telegram channel intel signals (Tranche 4).",
        tags=("intel", "social"),
    ),
    SourceQualityEntry(
        name="threat_intel",
        lookahead_hours=DEFAULT_OUTCOME_WINDOW_HOURS,
        description="Threat-intel feed (CISA / NVD).",
        tags=("intel", "security"),
    ),
    SourceQualityEntry(
        name="convergence_watchlist",
        lookahead_hours=DEFAULT_OUTCOME_WINDOW_HOURS,
        description="Sovereign-thesis convergence watchlist.",
        tags=("intel", "research"),
    ),
    SourceQualityEntry(
        name="sovereign_thesis",
        lookahead_hours=DEFAULT_OUTCOME_WINDOW_HOURS,
        description="Sovereign thesis source.",
        tags=("intel", "research"),
    ),
    # ── Tranche 6 Lane 7 — SEC + earnings call sources. ──────────────────
    # Lookahead bumps to 72h: SEC filings and earnings calls have slower
    # price-discovery half-lives than ordinary TA signals (the market often
    # takes a couple of trading days to fully price the headline).
    SourceQualityEntry(
        name="sec_edgar",
        lookahead_hours=72,
        description=(
            "SEC EDGAR filings (8-K / 10-Q / 10-K). Direction comes from "
            "the deterministic SEC classifier — no LLM in the path."
        ),
        tags=("sec", "filings", "regulated", "tranche-7"),
    ),
    SourceQualityEntry(
        name="earnings_calls",
        lookahead_hours=72,
        description=(
            "Earnings call transcripts (free-tier IR RSS only). Direction "
            "comes from a deterministic sentiment heuristic; we do not "
            "wire paid providers."
        ),
        tags=("earnings", "filings", "tranche-7"),
    ),
)


# Process-local mutable mirror of the default registrations. The default
# entries are seeded on import; downstream callers can register additional
# sources without modifying this module.
_REGISTRY: dict[str, SourceQualityEntry] = {e.name: e for e in BUILTIN_SOURCES}


def default_registry() -> dict[str, SourceQualityEntry]:
    """Return a *copy* of the current registry.

    The returned dict is a shallow copy — mutating it does NOT mutate the
    process-local registry. Use :func:`register_source` to add entries.
    """
    return dict(_REGISTRY)


def register_source(entry: SourceQualityEntry) -> None:
    """Register or replace a source.

    This is idempotent: registering the same entry twice yields the same
    final state. Replacing an existing name with a new entry is allowed
    (Tranche 7 adapters may want to bump ``lookahead_hours`` based on
    observed half-life).
    """
    if not isinstance(entry, SourceQualityEntry):
        raise TypeError(f"register_source expects SourceQualityEntry, got {type(entry)!r}")
    _REGISTRY[entry.name] = entry


def registered_sources() -> tuple[str, ...]:
    """Return the canonical source names currently registered, sorted."""
    return tuple(sorted(_REGISTRY.keys()))


def source_signal_to_record(
    source_signal: Any,
    *,
    confidence_default: float = 1.0,
) -> SignalRecord:
    """Convert a ``lib.correlator.sources.SourceSignal`` to a ``SignalRecord``.

    We accept ``Any`` rather than the concrete type to keep the import
    graph one-way; the caller is responsible for passing a SourceSignal
    instance. The function reads only the public attributes the
    SourceSignal contract documents:

    - ``source: str``
    - ``symbol: str``
    - ``direction: str``  ("bull" | "bear" | "neutral")
    - ``confidence: float``  (0.0 .. 1.0)
    - ``timestamp_iso: str``  (ISO-8601 UTC)
    """
    timestamp_iso = getattr(source_signal, "timestamp_iso", "") or ""
    if timestamp_iso:
        try:
            ts = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        except ValueError:
            ts = datetime.now(UTC)
    else:
        ts = datetime.now(UTC)
    return SignalRecord(
        source=str(getattr(source_signal, "source", "unknown")),
        symbol=str(getattr(source_signal, "symbol", "")),
        timestamp=ts,
        direction=str(getattr(source_signal, "direction", "neutral")),
        confidence=float(
            getattr(source_signal, "confidence", confidence_default) or confidence_default
        ),
    )


def records_for_sources(
    source_signals: Iterable[Any],
    *,
    only: Iterable[str] | None = None,
) -> list[SignalRecord]:
    """Convert many ``SourceSignal`` instances, optionally filtered by name."""
    allow = set(only) if only else None
    out: list[SignalRecord] = []
    for s in source_signals:
        name = str(getattr(s, "source", "unknown"))
        if allow is not None and name not in allow:
            continue
        out.append(source_signal_to_record(s))
    return out
