"""Deterministic rubric for narrative theses.

The rubric is intentionally pure and non-LLM. It mirrors the Vertex eval
approach: reproducible scores, explicit notes, and simple gates that keep weak
or structurally invalid prose out of published narrative artifacts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

MIN_RUBRIC_SCORE_TO_PUBLISH = 0.7

IMPLIED_POSITIONS: tuple[str, ...] = (
    "long_strong",
    "long_mild",
    "neutral",
    "short_mild",
    "short_strong",
    "no_position",
)

_NUMERIC_FACT = re.compile(
    r"[-+]?\b\d{1,4}(?:\.\d+)?\s?(?:%|bps|usd|eth|btc|sol|x|h|d|m|w)?\b",
    re.IGNORECASE,
)
_SOURCE_HINT = re.compile(
    r"\b(?:source|sources|corroborated|divergent|bull|bear|neutral|consensus|edge_score|"
    r"tradingview|telegram|hyperliquid|threat|kronos|scanner|sovereign|watchlist)\b",
    re.IGNORECASE,
)
_HEDGE_WORDS = re.compile(
    r"\b(?:if|unless|could|may|might|risk|caveat|invalidat|counter|however|research-only|"
    r"dry-run|not a trade|no live)\b",
    re.IGNORECASE,
)
_ACTION_WORDS = (
    "watch",
    "monitor",
    "compare",
    "confirm",
    "invalidate",
    "recheck",
    "review",
    "wait",
    "flag",
    "measure",
)


@dataclass(frozen=True)
class NarrativeRubricScore:
    structural_validity: float
    actionability: float
    citation_density: float
    internal_consistency: float
    hedging_appropriateness: float
    overall: float
    publishable: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["notes"] = list(self.notes)
        return out


def _as_mapping(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    return {}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [chunk.strip() for chunk in re.split(r"\n+|;|•", value) if chunk.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def _structural(payload: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    scalar_fields = (
        "thesis_one_paragraph",
        "counter_thesis_one_paragraph",
        "next_signal_to_watch",
        "caveat_block",
    )
    score = 0.0
    for field_name in scalar_fields:
        value = payload.get(field_name)
        if isinstance(value, str) and _word_count(value) >= 3:
            score += 0.12
        else:
            notes.append(f"{field_name}_missing_or_too_short")

    evidence = _as_list(payload.get("evidence_bullets"))
    invalidators = _as_list(payload.get("invalidators"))
    if len(evidence) >= 3:
        score += 0.22
    else:
        notes.append("fewer_than_three_evidence_bullets")
    if len(invalidators) >= 3:
        score += 0.18
    else:
        notes.append("fewer_than_three_invalidators")
    if payload.get("implied_position") in IMPLIED_POSITIONS:
        score += 0.07
    else:
        notes.append("invalid_implied_position")
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = -1.0
    if 0.0 <= confidence <= 1.0:
        score += 0.05
    else:
        notes.append("confidence_out_of_range")
    return _clamp(score), notes


def _actionability(payload: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    invalidators = _as_list(payload.get("invalidators"))
    next_signal = str(payload.get("next_signal_to_watch") or "").strip().lower()
    concrete_invalidators = [item for item in invalidators if _word_count(item) >= 4]
    score = min(0.55, len(concrete_invalidators) * 0.15)
    if any(word in next_signal for word in _ACTION_WORDS) and _word_count(next_signal) >= 4:
        score += 0.25
    else:
        notes.append("next_signal_not_actionable")
    if payload.get("implied_position") != "no_position":
        score += 0.1
    if "research" in str(payload.get("caveat_block") or "").lower():
        score += 0.1
    else:
        notes.append("caveat_missing_research_context")
    return _clamp(score), notes


def _citation_density(payload: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    evidence = _as_list(payload.get("evidence_bullets"))
    blob = "\n".join(
        evidence
        + [
            str(payload.get("thesis_one_paragraph") or ""),
            str(payload.get("counter_thesis_one_paragraph") or ""),
            str(payload.get("next_signal_to_watch") or ""),
        ]
    )
    if not evidence:
        return 0.0, ["no_evidence_for_citation_density"]
    source_hits = len(_SOURCE_HINT.findall(blob))
    numeric_hits = len(_NUMERIC_FACT.findall(blob))
    score = min(
        1.0, (len(evidence) / 5.0) * 0.45 + (source_hits / 6.0) * 0.35 + (numeric_hits / 6.0) * 0.2
    )
    if score < 0.5:
        notes.append("low_source_or_numeric_density")
    return _clamp(score), notes


def _edge_from_signal(signal: Any | None) -> float | None:
    if signal is None:
        return None
    payload = _as_mapping(signal)
    try:
        return float(payload.get("edge_score"))
    except (TypeError, ValueError):
        return None


def _internal_consistency(payload: dict[str, Any], signal: Any | None) -> tuple[float, list[str]]:
    notes: list[str] = []
    position = payload.get("implied_position")
    edge = _edge_from_signal(signal)
    if edge is None:
        return 0.75, ["signal_edge_unavailable"]
    if edge >= 0.65 and position != "long_strong":
        notes.append("strong_positive_edge_not_long_strong")
        return 0.45, notes
    if 0.2 < edge < 0.65 and position != "long_mild":
        notes.append("positive_edge_not_long_mild")
        return 0.55, notes
    if -0.2 <= edge <= 0.2 and position not in {"neutral", "no_position"}:
        notes.append("flat_edge_has_directional_position")
        return 0.45, notes
    if -0.65 < edge < -0.2 and position != "short_mild":
        notes.append("negative_edge_not_short_mild")
        return 0.55, notes
    if edge <= -0.65 and position != "short_strong":
        notes.append("strong_negative_edge_not_short_strong")
        return 0.45, notes
    consensus = str(_as_mapping(signal).get("consensus") or "")
    if consensus == "INSUFFICIENT_DATA" and position != "no_position":
        notes.append("insufficient_data_should_be_no_position")
        return 0.35, notes
    return 1.0, notes


def _hedging(payload: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    counter = str(payload.get("counter_thesis_one_paragraph") or "")
    caveat = str(payload.get("caveat_block") or "")
    invalidators = _as_list(payload.get("invalidators"))
    score = 0.0
    if _word_count(counter) >= 10 and _HEDGE_WORDS.search(counter):
        score += 0.35
    else:
        notes.append("counter_thesis_not_hedged")
    if len(invalidators) >= 3:
        score += 0.3
    else:
        notes.append("invalidators_missing")
    if _HEDGE_WORDS.search(caveat) and _word_count(caveat) >= 8:
        score += 0.35
    else:
        notes.append("caveat_not_hedged")
    return _clamp(score), notes


def score_narrative(
    thesis: Any,
    *,
    signal: Any | None = None,
    min_publish_score: float = MIN_RUBRIC_SCORE_TO_PUBLISH,
) -> NarrativeRubricScore:
    payload = _as_mapping(thesis)
    notes: list[str] = []
    structural, structural_notes = _structural(payload)
    actionability, action_notes = _actionability(payload)
    citation, citation_notes = _citation_density(payload)
    consistency, consistency_notes = _internal_consistency(payload, signal)
    hedging, hedge_notes = _hedging(payload)
    notes.extend(structural_notes)
    notes.extend(action_notes)
    notes.extend(citation_notes)
    notes.extend(consistency_notes)
    notes.extend(hedge_notes)
    overall = _clamp((structural + actionability + citation + consistency + hedging) / 5.0)
    return NarrativeRubricScore(
        structural_validity=structural,
        actionability=actionability,
        citation_density=citation,
        internal_consistency=consistency,
        hedging_appropriateness=hedging,
        overall=overall,
        publishable=overall >= min_publish_score,
        notes=tuple(notes),
    )


__all__ = [
    "IMPLIED_POSITIONS",
    "MIN_RUBRIC_SCORE_TO_PUBLISH",
    "NarrativeRubricScore",
    "score_narrative",
]
