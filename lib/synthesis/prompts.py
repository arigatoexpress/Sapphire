"""Versioned prompts for Sapphire's narrative synthesis engine.

Prompt text is centralized here so live model changes are explicit and
reviewable. The dry-run path also uses the same compact signal rendering,
which keeps tests deterministic and makes prompt-size caps auditable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

PROMPT_VERSION = "narrative-thesis-v0.1.0"
RUBRIC_VERSION = "narrative-rubric-v0.1.0"

SYSTEM_PROMPT = (
    "You are Sapphire's LLM Narrative Synthesis Engine. You turn a single "
    "provenance-stamped CorrelatedSignal into a strict JSON NarrativeThesis. "
    "You do not recommend real trade execution, send messages, expose secrets, "
    "or invent facts not present in the input. Keep claims tied to source names, "
    "numbers, consensus labels, and explicit caveats. Reply with JSON only."
)

NARRATIVE_SCHEMA: dict[str, Any] = {
    "thesis_one_paragraph": "2-5 sentence explanation of why the edge exists.",
    "evidence_bullets": ["3-7 bullets tied to source names or numeric fields."],
    "counter_thesis_one_paragraph": "1-3 sentence plausible bear/base counter-case.",
    "invalidators": ["3-6 concrete signals that would invalidate the thesis."],
    "next_signal_to_watch": "one next observable signal.",
    "implied_position": (
        "one of long_strong, long_mild, neutral, short_mild, short_strong, no_position"
    ),
    "confidence": "float from 0.0 to 1.0",
    "caveat_block": "short caveat; must say research-only or dry-run when applicable.",
}

RUBRIC_TEXT = (
    f"Rubric {RUBRIC_VERSION}: score structural_validity, actionability, "
    "citation_density, internal_consistency, and hedging_appropriateness in [0, 1]. "
    "A thesis is publishable only when the average score is at least 0.70."
)

_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "private_key",
    "authorization",
    "cookie",
    "session",
)


def _redact_sensitive_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
                out[key] = "[redacted]"
            else:
                out[key] = _redact_sensitive_keys(raw_value)
        return out
    if isinstance(value, list):
        return [_redact_sensitive_keys(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_sensitive_keys(item) for item in value]
    return value


def compact_signal_payload(signal: Mapping[str, Any], *, max_chars: int) -> dict[str, Any]:
    """Return a deterministic, redacted signal payload within ``max_chars``."""
    compact = _redact_sensitive_keys(dict(signal))
    text = json.dumps(compact, sort_keys=True, separators=(",", ":"), default=str)
    if len(text) <= max_chars:
        return compact
    keep = {
        "symbol": compact.get("symbol"),
        "timeframe": compact.get("timeframe"),
        "edge_score": compact.get("edge_score"),
        "consensus": compact.get("consensus"),
        "corroborated_by": compact.get("corroborated_by"),
        "divergent_sources": compact.get("divergent_sources"),
        "bull_sources": compact.get("bull_sources"),
        "bear_sources": compact.get("bear_sources"),
        "neutral_sources": compact.get("neutral_sources"),
        "freshness_seconds": compact.get("freshness_seconds"),
        "contributing": compact.get("contributing"),
        "raw_score": compact.get("raw_score"),
        "agreement_multiplier": compact.get("agreement_multiplier"),
        "contradict_factor": compact.get("contradict_factor"),
        "total_weight": compact.get("total_weight"),
        "generated_at": compact.get("generated_at"),
        "provenance_envelope": compact.get("provenance_envelope"),
        "truncated": True,
    }
    text = json.dumps(keep, sort_keys=True, separators=(",", ":"), default=str)
    if len(text) <= max_chars:
        return keep
    keep["provenance_envelope"] = {"truncated": True}
    return keep


def build_user_prompt(
    signal: Mapping[str, Any],
    *,
    max_input_chars: int,
    mode: str = "dry-run",
) -> str:
    """Render the canonical live prompt for one correlated signal."""
    compact = compact_signal_payload(signal, max_chars=max_input_chars)
    signal_json = json.dumps(compact, indent=2, sort_keys=True, default=str)
    prompt = (
        f"Prompt version: {PROMPT_VERSION}\n"
        f"Mode requested: {mode}\n\n"
        "Return a JSON object with exactly this schema:\n"
        f"{json.dumps(NARRATIVE_SCHEMA, indent=2, sort_keys=True)}\n\n"
        "Rules:\n"
        "- Use only facts present in the CorrelatedSignal.\n"
        "- Mention source names when describing evidence.\n"
        "- Include a credible counter-thesis and at least three invalidators.\n"
        "- Keep the caveat block research-only; do not imply live trading.\n"
        "- Do not include secrets, credentials, raw private payloads, or code fences.\n"
        "- If the evidence is insufficient, choose no_position and explain why.\n\n"
        f"{RUBRIC_TEXT}\n\n"
        "CorrelatedSignal:\n"
        f"{signal_json}"
    )
    if len(prompt) <= max_input_chars:
        return prompt
    return prompt[: max_input_chars - 1] + "\n"


def build_messages(
    signal: Mapping[str, Any], *, max_input_chars: int, mode: str
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(signal, max_input_chars=max_input_chars, mode=mode),
        },
    ]


__all__ = [
    "NARRATIVE_SCHEMA",
    "PROMPT_VERSION",
    "RUBRIC_TEXT",
    "RUBRIC_VERSION",
    "SYSTEM_PROMPT",
    "build_messages",
    "build_user_prompt",
    "compact_signal_payload",
]
