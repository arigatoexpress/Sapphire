"""Tests for the Narrative Synthesis Engine."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pytest

from lib.synthesis import narrative_engine as engine
from lib.synthesis.rubric import score_narrative

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)


def _signal(edge: float = 0.72, consensus: str = "AGREE_BULL", contributing: int = 4) -> dict:
    bull_sources = ["tradingview", "kronos_forecast"] if edge > 0 else []
    bear_sources = ["hyperliquid", "ta_scanner"] if edge < 0 else []
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "edge_score": edge,
        "consensus": consensus,
        "corroborated_by": bull_sources or bear_sources,
        "divergent_sources": ["threat_intel"] if consensus == "CONTRADICT" else [],
        "bull_sources": bull_sources,
        "bear_sources": bear_sources,
        "neutral_sources": ["sovereign_thesis"] if abs(edge) <= 0.2 else [],
        "freshness_seconds": 90,
        "contributing": contributing,
        "raw_score": edge * 0.9,
        "agreement_multiplier": 1.2,
        "contradict_factor": 1.0,
        "total_weight": 3.4,
        "generated_at": "2026-04-28T11:59:00+00:00",
        "provenance_envelope": {"generator": "lib.correlator.engine"},
    }


@pytest.fixture
def isolated_engine(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    secrets_file = tmp_path / "secrets.env"
    monkeypatch.setattr(engine, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(engine, "COUNTER_PATH", cache_dir / "counters.json")
    monkeypatch.setattr(engine, "SECRETS_FILE", secrets_file)
    monkeypatch.delenv("SAPPHIRE_NARRATIVE_LIVE", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    return cache_dir, secrets_file


def test_dry_run_default_returns_publishable_thesis(isolated_engine) -> None:
    out = engine.synthesize(_signal(), now=FROZEN_NOW)
    assert out["ok"] is True
    assert out["metadata"]["mode_actual"] == "dry-run"
    assert out["thesis"]["implied_position"] == "long_strong"
    assert out["rubric"]["publishable"] is True


def test_synthesize_thesis_accepts_correlated_signal_like_dataclass(isolated_engine) -> None:
    class _Sig:
        def to_dict(self):
            return _signal()

    thesis = engine.synthesize_thesis(_Sig(), now=FROZEN_NOW)
    assert thesis.symbol == "BTC"
    assert thesis.provenance_envelope["source_signal_hash"]


def test_live_request_blocks_without_env(isolated_engine) -> None:
    thesis = engine.synthesize_thesis(_signal(), mode="live", now=FROZEN_NOW)
    assert thesis.mode_actual == "dry-run-blocked-by-env"


def test_live_request_blocks_without_key(isolated_engine, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE", "1")
    thesis = engine.synthesize_thesis(_signal(), mode="live", now=FROZEN_NOW)
    assert thesis.mode_actual == "dry-run-no-key"


def test_live_request_runs_sensitivity_gate(isolated_engine, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    monkeypatch.setattr(engine, "_sensitivity", lambda _prompt: (True, "secret"))
    thesis = engine.synthesize_thesis(_signal(), mode="live", now=FROZEN_NOW)
    assert thesis.mode_actual == "dry-run-safety"
    assert thesis.provenance_envelope["sensitivity"]["reason"] == "secret"


@pytest.mark.parametrize(
    ("edge", "consensus", "contributing", "expected"),
    [
        (0.80, "AGREE_BULL", 3, "long_strong"),
        (0.30, "PARTIAL_BULL", 1, "long_mild"),
        (0.0, "NEUTRAL", 2, "neutral"),
        (-0.30, "PARTIAL_BEAR", 1, "short_mild"),
        (-0.80, "AGREE_BEAR", 3, "short_strong"),
        (0.0, "INSUFFICIENT_DATA", 0, "no_position"),
    ],
)
def test_all_implied_position_values_are_reachable(edge, consensus, contributing, expected) -> None:
    assert engine.implied_position_for_edge(_signal(edge, consensus, contributing)) == expected


def test_rubric_gate_marks_dry_run_publishable(isolated_engine) -> None:
    thesis = engine.synthesize_thesis(_signal(0.3, "PARTIAL_BULL", 1), now=FROZEN_NOW)
    rubric = score_narrative(thesis, signal=_signal(0.3, "PARTIAL_BULL", 1))
    assert rubric.overall >= engine.MIN_RUBRIC_SCORE_TO_PUBLISH


def test_rate_limit_falls_back_before_sdk_call(isolated_engine, monkeypatch) -> None:
    cache_dir, _ = isolated_engine
    cache_dir.mkdir(parents=True)
    (cache_dir / "counters.json").write_text(
        json.dumps({"calls": [time.time()] * engine.MAX_CALLS_PER_HOUR, "month_tokens": 0}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    thesis = engine.synthesize_thesis(
        _signal(),
        mode="live",
        sdk_call=lambda *a, **k: pytest.fail("sdk should not be called"),
        now=FROZEN_NOW,
    )
    assert thesis.mode_actual == "dry-run-rate-limited"


def test_live_success_caches_and_cache_short_circuits(isolated_engine, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    calls: list[str] = []

    def sdk(prompt, **_kwargs):
        calls.append(prompt)
        return {
            "text": json.dumps(
                {
                    "thesis_one_paragraph": "BTC is supported by edge_score 0.72 and source tradingview.",
                    "evidence_bullets": [
                        "edge_score 0.72 from source tradingview",
                        "consensus AGREE_BULL across 4 sources",
                        "freshness_seconds 90 keeps the source current",
                    ],
                    "counter_thesis_one_paragraph": "However, if divergent sources expand, the thesis could weaken.",
                    "invalidators": [
                        "Watch edge_score delta below 0.10 against the thesis",
                        "Monitor divergent_sources expanding above 2 feeds",
                        "Confirm freshness_seconds stays below the hard limit",
                    ],
                    "next_signal_to_watch": "Watch the next BTC 1h correlated signal row.",
                    "implied_position": "long_strong",
                    "confidence": 0.81,
                    "caveat_block": "Research-only dry-run narrative; no live trade execution.",
                }
            ),
            "prompt_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
        }

    first = engine.synthesize_thesis(_signal(), mode="live", sdk_call=sdk, now=FROZEN_NOW)
    second = engine.synthesize_thesis(
        _signal(),
        mode="live",
        sdk_call=lambda *a, **k: pytest.fail("cache should short-circuit"),
        now=FROZEN_NOW,
    )
    assert first.mode_actual == "live"
    assert second.mode_actual == "live-cache"
    assert len(calls) == 1


def test_live_unparseable_response_falls_back(isolated_engine, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    thesis = engine.synthesize_thesis(
        _signal(),
        mode="live",
        sdk_call=lambda *a, **k: {"text": "not json", "total_tokens": 1},
        now=FROZEN_NOW,
    )
    assert thesis.mode_actual == "dry-run-live-unparseable"


def test_max_output_tokens_are_clamped_for_live_call(isolated_engine, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    seen: dict[str, int] = {}

    def sdk(_prompt, **kwargs):
        seen["max_output_tokens"] = kwargs["max_output_tokens"]
        return {
            "text": json.dumps(_good_live_payload()),
            "prompt_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }

    engine.synthesize_thesis(_signal(), mode="live", max_output_tokens=99_999, sdk_call=sdk)
    assert seen["max_output_tokens"] == engine.MAX_OUTPUT_TOKENS_HARD


def test_unknown_model_returns_error(isolated_engine) -> None:
    out = engine.synthesize(_signal(), model="not-real")
    assert out["ok"] is False
    assert "unknown model" in out["error"]


def test_status_reports_caps_without_secrets(isolated_engine, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    snap = engine.status()
    assert snap["max_calls_per_hour"] == 6
    assert snap["max_tokens_per_month"] == 750_000
    assert "super-secret" not in json.dumps(snap)


def _good_live_payload() -> dict:
    return {
        "thesis_one_paragraph": "BTC is supported by edge_score 0.72 and source tradingview.",
        "evidence_bullets": [
            "edge_score 0.72 from source tradingview",
            "consensus AGREE_BULL across 4 sources",
            "freshness_seconds 90 keeps the source current",
        ],
        "counter_thesis_one_paragraph": "However, if divergent sources expand, the thesis could weaken.",
        "invalidators": [
            "Watch edge_score delta below 0.10 against the thesis",
            "Monitor divergent_sources expanding above 2 feeds",
            "Confirm freshness_seconds stays below the hard limit",
        ],
        "next_signal_to_watch": "Watch the next BTC 1h correlated signal row.",
        "implied_position": "long_strong",
        "confidence": 0.81,
        "caveat_block": "Research-only dry-run narrative; no live trade execution.",
    }
