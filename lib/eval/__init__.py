"""Sapphire eval harnesses.

Pure-logic modules for benchmarking external AI lanes against the local
4-tier inference mesh. No I/O, no env vars, no network — these libraries
are the deterministic scoring core that plugin tools wrap.

Modules:
  - vertex_harness — Vertex/Gemini OODA rubric + canonical prompt sets.
"""

from .vertex_harness import (
    EVAL_PROMPT_SETS,
    OODA_KEYS,
    PROMPT_SET_NAMES,
    AggregateScores,
    PromptCase,
    RubricScores,
    aggregate_scores,
    deterministic_mock_response,
    enforce_caps,
    get_prompt_set,
    score_response,
)

__all__ = [
    "EVAL_PROMPT_SETS",
    "OODA_KEYS",
    "PROMPT_SET_NAMES",
    "AggregateScores",
    "PromptCase",
    "RubricScores",
    "aggregate_scores",
    "deterministic_mock_response",
    "enforce_caps",
    "get_prompt_set",
    "score_response",
]
