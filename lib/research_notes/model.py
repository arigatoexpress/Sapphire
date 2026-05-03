"""Research note data contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResearchNote:
    """Structured research memo composed from local Sapphire artifacts."""

    note_id: str
    as_of_date: str
    strategy_slug: str
    strategy_name: str
    title: str
    subtitle: str
    thesis: str
    counter_thesis: str
    key_metrics: dict[str, Any]
    backtest_summary: dict[str, Any]
    performance_summary: dict[str, Any]
    context: dict[str, Any]
    chart_specs: list[dict[str, Any]]
    evidence: list[str]
    invalidators: list[str]
    next_steps: list[str]
    caveat: str
    sources: list[str]
    generated_at: str
    version: str = "0.1.0"
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
