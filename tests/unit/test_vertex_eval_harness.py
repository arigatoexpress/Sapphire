"""Unit tests for ``lib.eval.vertex_harness`` — pure scoring logic.

These tests must run without any environment variables, network access,
or filesystem state. The harness module is the deterministic core of the
``vertex_eval`` plugin tool, so the rubric is what an external auditor
re-runs to check the operator's claim that "Gemini outputs are X% better
than the local mesh on these prompts".
"""

from __future__ import annotations

import json

from lib.eval.vertex_harness import (
    EVAL_PROMPT_SETS,
    EVAL_PROMPTS_PER_RUN_HARD,
    MAX_INPUT_CHARS_HARD,
    MAX_OUTPUT_TOKENS_HARD,
    PROMPT_SET_NAMES,
    PromptCase,
    aggregate_scores,
    deterministic_mock_response,
    enforce_caps,
    get_prompt_set,
    score_response,
)


def _make_case(set_name: str = "test-set", prompt_id: str = "test-set-01") -> PromptCase:
    return PromptCase(
        set_name=set_name,
        prompt_id=prompt_id,
        topic="A short topic",
        context="A short context with one fact: 42 bps.",
        expected_focus=("focus_a",),
    )


def test_prompt_sets_are_immutable_constants():
    # All four documented prompt sets exist with the documented sizes.
    assert PROMPT_SET_NAMES == (
        "crypto-regime-shift",
        "vote-monitor-context",
        "threat-intel-summary",
        "sovereign-thesis-synthesis",
    )
    sizes = {name: len(EVAL_PROMPT_SETS[name]) for name in PROMPT_SET_NAMES}
    assert sizes == {
        "crypto-regime-shift": 3,
        "vote-monitor-context": 2,
        "threat-intel-summary": 2,
        "sovereign-thesis-synthesis": 2,
    }
    total_prompts = sum(sizes.values())
    assert total_prompts == 9
    # Total prompts must stay strictly under the per-run hard cap.
    assert total_prompts < EVAL_PROMPTS_PER_RUN_HARD
    # Each case carries a well-formed identifier for cross-referencing.
    for name in PROMPT_SET_NAMES:
        for case in EVAL_PROMPT_SETS[name]:
            assert case.set_name == name
            assert case.prompt_id.startswith(name)
            assert case.topic.strip()
            assert case.context.strip()


def test_get_prompt_set_returns_empty_for_unknown_name():
    assert get_prompt_set("does-not-exist") == ()
    assert len(get_prompt_set("crypto-regime-shift")) == 3


def test_enforce_caps_passes_default_request():
    ok, reason = enforce_caps(prompt_count=9, max_output_tokens=512, input_chars=2000)
    assert ok is True
    assert reason == ""


def test_enforce_caps_blocks_too_many_prompts():
    ok, reason = enforce_caps(
        prompt_count=EVAL_PROMPTS_PER_RUN_HARD + 1,
        max_output_tokens=512,
        input_chars=1000,
    )
    assert ok is False
    assert "prompts_per_run_breach" in reason


def test_enforce_caps_blocks_oversized_output_tokens():
    ok, reason = enforce_caps(
        prompt_count=1, max_output_tokens=MAX_OUTPUT_TOKENS_HARD + 1, input_chars=1000
    )
    assert ok is False
    assert "output_tokens_breach" in reason


def test_enforce_caps_blocks_oversized_input_chars():
    ok, reason = enforce_caps(
        prompt_count=1, max_output_tokens=512, input_chars=MAX_INPUT_CHARS_HARD + 1
    )
    assert ok is False
    assert "input_chars_breach" in reason


def test_deterministic_mock_response_is_stable_and_well_formed():
    case = _make_case()
    first = deterministic_mock_response(case)
    second = deterministic_mock_response(case)
    assert first == second
    assert set(first.keys()) == {"observe", "orient", "decide", "act"}
    assert isinstance(first["act"], list)
    assert len(first["act"]) >= 2


def test_score_response_perfect_oods_packet():
    case = _make_case()
    response = {
        "observe": "BTC funding at 0.005% with OI up 4.1%.",
        "orient": "Regime ROTATING. Sapphire posture FLAT. See [BTC](https://x).",
        "decide": "Hold paper book; raise alert thresholds 50 bps.",
        "act": [
            "Monitor open interest 4h reading.",
            "Run signal scanner against BTC perp.",
            "Update dashboard polling to 5 second cadence.",
            "Schedule review at 12:00 UTC.",
        ],
    }
    scores = score_response(
        response,
        case=case,
        latency_ms=812,
        tokens_used=410,
        max_output_tokens=512,
    )
    assert scores.structural_validity == 1.0
    assert scores.actionability == 1.0
    assert scores.citation_density > 0.4
    assert scores.latency_ms == 812
    assert scores.tokens_used == 410
    assert scores.caps_breach is False
    assert scores.notes == ()


def test_score_response_missing_keys_lowers_structural_score():
    case = _make_case()
    response = {"observe": "BTC up", "orient": "OK"}  # missing decide + act
    scores = score_response(
        response,
        case=case,
        latency_ms=0,
        tokens_used=0,
        max_output_tokens=128,
    )
    assert scores.structural_validity == 0.5
    assert "missing_decide" in scores.notes
    assert "missing_act" in scores.notes
    # actionability bottoms out at 0 when act is absent.
    assert scores.actionability == 0.0


def test_score_response_handles_string_input_via_json_parse():
    case = _make_case()
    payload = json.dumps(
        {
            "observe": "Regime check.",
            "orient": "Sapphire posture.",
            "decide": "Defer external spend.",
            "act": ["Run mesh probe.", "Verify dashboard panel."],
        }
    )
    scores = score_response(
        payload,
        case=case,
        latency_ms=10,
        tokens_used=5,
        max_output_tokens=128,
    )
    assert scores.structural_validity == 1.0
    assert scores.actionability >= 0.5
    # No citations / numbers, so citation density is zero.
    assert scores.citation_density == 0.0


def test_score_response_handles_garbage_input_gracefully():
    case = _make_case()
    scores = score_response(
        "this is not JSON",
        case=case,
        latency_ms=0,
        tokens_used=0,
        max_output_tokens=64,
    )
    assert scores.structural_validity == 0.0
    assert scores.actionability == 0.0
    assert scores.citation_density == 0.0
    assert "non_dict_response" in scores.notes


def test_score_response_flags_caps_breach_on_oversized_input():
    case = PromptCase(
        set_name="caps",
        prompt_id="caps-01",
        topic="x",
        context="y" * (MAX_INPUT_CHARS_HARD + 10),
    )
    scores = score_response(
        {"observe": "x", "orient": "x", "decide": "x", "act": ["Run x.", "Verify y."]},
        case=case,
        latency_ms=0,
        tokens_used=0,
        max_output_tokens=128,
    )
    assert scores.caps_breach is True


def test_score_response_actionability_requires_concrete_verbs():
    case = _make_case()
    # Non-verb act entries don't count as concrete steps.
    response = {
        "observe": "x",
        "orient": "x",
        "decide": "x",
        "act": ["the cat sat on", "philosophical musings"],
    }
    scores = score_response(
        response,
        case=case,
        latency_ms=0,
        tokens_used=0,
        max_output_tokens=128,
    )
    assert scores.actionability == 0.0


def test_aggregate_scores_handles_empty_input():
    agg = aggregate_scores([])
    assert agg.n == 0
    assert agg.structural_validity_mean == 0.0


def test_aggregate_scores_means_and_minimums():
    case = _make_case()
    high = score_response(
        {
            "observe": "BTC funding 0.005% on Binance.",
            "orient": "Sapphire flat 40% USD.",
            "decide": "Hold posture, monitor 4h.",
            "act": ["Run scan.", "Verify monitor.", "Send alert.", "Schedule review."],
        },
        case=case,
        latency_ms=500,
        tokens_used=200,
        max_output_tokens=512,
    )
    low = score_response(
        {"observe": "x"},
        case=case,
        latency_ms=1500,
        tokens_used=50,
        max_output_tokens=512,
    )
    agg = aggregate_scores([high, low])
    assert agg.n == 2
    assert agg.tokens_used_total == 250
    assert agg.latency_ms_mean == 1000.0
    # Min is the worst per-prompt structural score.
    assert agg.structural_validity_min == low.structural_validity
    assert agg.structural_validity_mean > agg.structural_validity_min


def test_score_dict_round_trip_is_json_safe():
    case = _make_case()
    scores = score_response(
        deterministic_mock_response(case),
        case=case,
        latency_ms=0,
        tokens_used=0,
        max_output_tokens=512,
    )
    blob = json.dumps(scores.to_dict())
    parsed = json.loads(blob)
    assert "structural_validity" in parsed
    assert isinstance(parsed["caps_breach"], bool)


def test_aggregate_scores_dict_round_trip_is_json_safe():
    case = _make_case()
    scores = [
        score_response(
            deterministic_mock_response(case),
            case=case,
            latency_ms=10,
            tokens_used=5,
            max_output_tokens=512,
        )
    ]
    agg = aggregate_scores(scores)
    blob = json.dumps(agg.to_dict())
    assert "structural_validity_mean" in blob
