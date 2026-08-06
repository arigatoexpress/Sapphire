"""Grok project library — paper-safe policy, genome, Win DC, research worker, loop.

This package is intentionally pure (no broker I/O, no Telegram, no secrets).
Plant/Claude wires it later. Cloud Shell / Grok web densify against it.
"""

from __future__ import annotations

from lib.grok.genome import GenomeLesson, LessonBook, lesson_from_closed_trade
from lib.grok.policy import (
    FREE_REIGN_DEFAULTS,
    Decision,
    OrderProposal,
    evaluate_proposal,
    evaluate_scale_out,
    is_dens_blocked,
)
from lib.grok.research_worker import validate_research_manifest
from lib.grok.windows import evaluate_windows_acceptance
from lib.grok.system_brief import build_system_brief, write_brief
from lib.grok.free_reign_gate import GateRequest, GateResult, gate_order
from lib.grok.plant_outcomes import record_closed_trade
from lib.grok.bridge_client import pick_transport, smart_query, bridge_url_from_env

__all__ = [
    "FREE_REIGN_DEFAULTS",
    "Decision",
    "OrderProposal",
    "evaluate_proposal",
    "evaluate_scale_out",
    "is_dens_blocked",
    "GenomeLesson",
    "LessonBook",
    "lesson_from_closed_trade",
    "validate_research_manifest",
    "evaluate_windows_acceptance",
    "build_system_brief",
    "write_brief",
    "GateRequest",
    "GateResult",
    "gate_order",
    "record_closed_trade",
    "pick_transport",
    "smart_query",
    "bridge_url_from_env",
]

__version__ = "0.1.0"
