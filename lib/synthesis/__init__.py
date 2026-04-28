"""Narrative synthesis primitives for Sapphire correlated signals."""

from __future__ import annotations

from lib.synthesis.narrative_engine import (
    DEFAULT_MODEL,
    GENERATOR,
    MAX_CALLS_PER_HOUR,
    MAX_INPUT_CHARS_HARD,
    MAX_OUTPUT_TOKENS_HARD,
    MAX_TOKENS_PER_MONTH,
    MIN_RUBRIC_SCORE_TO_PUBLISH,
    VERSION,
    NarrativeThesis,
    implied_position_for_edge,
    status,
    synthesize,
    synthesize_thesis,
)
from lib.synthesis.prompts import PROMPT_VERSION, RUBRIC_VERSION, build_user_prompt
from lib.synthesis.rubric import NarrativeRubricScore, score_narrative

__all__ = [
    "DEFAULT_MODEL",
    "GENERATOR",
    "MAX_CALLS_PER_HOUR",
    "MAX_INPUT_CHARS_HARD",
    "MAX_OUTPUT_TOKENS_HARD",
    "MAX_TOKENS_PER_MONTH",
    "MIN_RUBRIC_SCORE_TO_PUBLISH",
    "PROMPT_VERSION",
    "RUBRIC_VERSION",
    "VERSION",
    "NarrativeRubricScore",
    "NarrativeThesis",
    "build_user_prompt",
    "implied_position_for_edge",
    "score_narrative",
    "status",
    "synthesize",
    "synthesize_thesis",
]
