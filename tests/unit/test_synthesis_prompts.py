"""Tests for versioned narrative prompts."""

from __future__ import annotations

from lib.synthesis import prompts


def _signal() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "edge_score": 0.5,
        "consensus": "PARTIAL_BULL",
        "corroborated_by": ["tradingview"],
        "api_key": "should-not-leak",
        "raw": {"password": "also-secret", "note": "ok"},
    }


def test_prompt_version_is_explicit() -> None:
    assert prompts.PROMPT_VERSION == "narrative-thesis-v0.1.0"


def test_rubric_version_is_explicit() -> None:
    assert prompts.RUBRIC_VERSION == "narrative-rubric-v0.1.0"


def test_prompt_mentions_json_schema() -> None:
    rendered = prompts.build_user_prompt(_signal(), max_input_chars=18_000)
    assert "Return a JSON object" in rendered
    assert "thesis_one_paragraph" in rendered


def test_prompt_redacts_sensitive_keys() -> None:
    rendered = prompts.build_user_prompt(_signal(), max_input_chars=18_000)
    assert "should-not-leak" not in rendered
    assert "also-secret" not in rendered
    assert "[redacted]" in rendered


def test_prompt_rendering_is_deterministic() -> None:
    assert prompts.build_user_prompt(_signal(), max_input_chars=18_000) == prompts.build_user_prompt(
        _signal(), max_input_chars=18_000
    )


def test_prompt_truncates_to_cap() -> None:
    signal = _signal()
    signal["raw"] = {"blob": "x" * 50_000}
    rendered = prompts.build_user_prompt(signal, max_input_chars=400)
    assert len(rendered) <= 400


def test_compact_payload_keeps_core_fields_when_truncated() -> None:
    signal = _signal()
    signal["raw"] = {"blob": "x" * 50_000}
    compact = prompts.compact_signal_payload(signal, max_chars=300)
    assert compact["symbol"] == "BTC"
    assert compact["edge_score"] == 0.5
    assert compact["truncated"] is True


def test_build_messages_has_system_and_user_roles() -> None:
    messages = prompts.build_messages(_signal(), max_input_chars=18_000, mode="dry-run")
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "Sapphire's LLM Narrative Synthesis Engine" in messages[0]["content"]
