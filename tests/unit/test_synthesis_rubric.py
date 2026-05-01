"""Tests for the deterministic narrative rubric."""

from __future__ import annotations

from lib.synthesis.narrative_engine import NarrativeThesis
from lib.synthesis.rubric import MIN_RUBRIC_SCORE_TO_PUBLISH, score_narrative


def _thesis(position: str = "long_strong") -> dict:
    return {
        "thesis_one_paragraph": (
            "BTC is supported by edge_score 0.72 and consensus AGREE_BULL across "
            "source tradingview and source hyperliquid."
        ),
        "evidence_bullets": [
            "edge_score 0.72 and raw_score 0.64 from source tradingview",
            "consensus AGREE_BULL across 4 sources and freshness_seconds 90",
            "agreement_multiplier 1.20 and total_weight 3.40 support the read",
        ],
        "counter_thesis_one_paragraph": (
            "However, if divergent sources expand or freshness decays, the thesis could weaken."
        ),
        "invalidators": [
            "Watch edge_score falling more than 0.10 against the thesis",
            "Monitor divergent_sources expanding to at least 2 feeds",
            "Confirm freshness_seconds remains below the hard limit",
        ],
        "next_signal_to_watch": "Watch the next BTC 1h correlated signal row for edge_score delta.",
        "implied_position": position,
        "confidence": 0.8,
        "caveat_block": "Research-only dry-run narrative; not a trade and no live execution.",
        "provenance_envelope": {"generator": "test"},
    }


def _signal(edge: float = 0.72, consensus: str = "AGREE_BULL") -> dict:
    return {"edge_score": edge, "consensus": consensus, "contributing": 4}


def test_complete_thesis_is_publishable() -> None:
    score = score_narrative(_thesis(), signal=_signal())
    assert score.publishable is True
    assert score.overall >= MIN_RUBRIC_SCORE_TO_PUBLISH


def test_missing_fields_are_not_publishable() -> None:
    score = score_narrative({"thesis_one_paragraph": "too thin"}, signal=_signal())
    assert score.publishable is False
    assert score.structural_validity < 0.5


def test_actionability_requires_next_signal() -> None:
    payload = _thesis()
    payload["next_signal_to_watch"] = "later"
    score = score_narrative(payload, signal=_signal())
    assert score.actionability < 1.0
    assert "next_signal_not_actionable" in score.notes


def test_citation_density_rewards_sources_and_numbers() -> None:
    weak = _thesis()
    weak["evidence_bullets"] = ["good source", "another source", "third source"]
    weak["thesis_one_paragraph"] = "BTC may be interesting, but the support is vague."
    weak["counter_thesis_one_paragraph"] = "However, the vague read could weaken."
    weak["next_signal_to_watch"] = "Watch the next market update."
    strong = _thesis()
    assert (
        score_narrative(strong, signal=_signal()).citation_density
        > score_narrative(weak, signal=_signal()).citation_density
    )


def test_internal_consistency_flags_wrong_position() -> None:
    score = score_narrative(_thesis("short_strong"), signal=_signal(0.8, "AGREE_BULL"))
    assert score.internal_consistency < 0.5
    assert "strong_positive_edge_not_long_strong" in score.notes


def test_internal_consistency_accepts_no_position_for_insufficient_data() -> None:
    payload = _thesis("no_position")
    score = score_narrative(payload, signal=_signal(0.0, "INSUFFICIENT_DATA"))
    assert score.internal_consistency == 1.0


def test_no_signal_gets_neutral_consistency_note() -> None:
    score = score_narrative(_thesis(), signal=None)
    assert score.internal_consistency == 0.75
    assert "signal_edge_unavailable" in score.notes


def test_invalid_confidence_reduces_structural_score() -> None:
    payload = _thesis()
    payload["confidence"] = 3
    score = score_narrative(payload, signal=_signal())
    assert "confidence_out_of_range" in score.notes


def test_hedging_requires_counter_and_caveat() -> None:
    payload = _thesis()
    payload["counter_thesis_one_paragraph"] = "No issue."
    payload["caveat_block"] = "Okay."
    score = score_narrative(payload, signal=_signal())
    assert score.hedging_appropriateness < 1.0


def test_score_is_idempotent() -> None:
    a = score_narrative(_thesis(), signal=_signal()).to_dict()
    b = score_narrative(_thesis(), signal=_signal()).to_dict()
    assert a == b


def test_rubric_accepts_dataclass_thesis() -> None:
    payload = _thesis()
    thesis = NarrativeThesis(
        thesis_one_paragraph=payload["thesis_one_paragraph"],
        evidence_bullets=payload["evidence_bullets"],
        counter_thesis_one_paragraph=payload["counter_thesis_one_paragraph"],
        invalidators=payload["invalidators"],
        next_signal_to_watch=payload["next_signal_to_watch"],
        implied_position="long_strong",
        confidence=0.8,
        caveat_block=payload["caveat_block"],
        provenance_envelope={},
    )
    assert score_narrative(thesis, signal=_signal()).publishable is True


def test_flat_edge_rejects_directional_position() -> None:
    score = score_narrative(_thesis("long_mild"), signal=_signal(0.0, "NEUTRAL"))
    assert score.internal_consistency < 0.5


def test_negative_edge_requires_short_bucket() -> None:
    score = score_narrative(_thesis("long_mild"), signal=_signal(-0.4, "PARTIAL_BEAR"))
    assert "negative_edge_not_short_mild" in score.notes


def test_strong_negative_edge_requires_short_strong() -> None:
    score = score_narrative(_thesis("short_mild"), signal=_signal(-0.8, "AGREE_BEAR"))
    assert "strong_negative_edge_not_short_strong" in score.notes
