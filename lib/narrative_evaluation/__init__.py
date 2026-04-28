"""Narrative self-evaluation loop for Sapphire theses."""

from lib.narrative_evaluation.aggregates import (
    aggregate_scores,
    calibration_report,
    diagnostics_report,
    summary_report,
)
from lib.narrative_evaluation.scoring import (
    DEFAULT_HORIZONS_HOURS,
    EvaluationOutcome,
    NarrativeEvaluationScore,
    score_thesis,
)

__all__ = [
    "DEFAULT_HORIZONS_HOURS",
    "EvaluationOutcome",
    "NarrativeEvaluationScore",
    "aggregate_scores",
    "calibration_report",
    "diagnostics_report",
    "score_thesis",
    "summary_report",
]
