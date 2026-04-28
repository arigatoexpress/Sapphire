"""Buyer-readable research note pipeline."""

from lib.research_notes.model import ResearchNote
from lib.research_notes.pipeline import (
    aggregate_summary,
    compose_note,
    latest_note,
    render_note,
)

__all__ = [
    "ResearchNote",
    "aggregate_summary",
    "compose_note",
    "latest_note",
    "render_note",
]
