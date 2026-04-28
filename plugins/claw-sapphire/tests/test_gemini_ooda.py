"""Tests for the Sapphire Gemini OODA synthesizer plugin tool.

Covers:
- the dry-run path produces a deterministic mock packet without contacting Google
- live mode requires the explicit ``SAPPHIRE_GEMINI_LIVE=1`` env flag
- sensitive prompts always fall back to the safety mock
- rate and cost caps trip cleanly into the mock
- the cache short-circuits repeat live calls
- the stdin JSON entry point matches the canonical Sapphire tool contract
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "gemini_ooda.py"

_spec = importlib.util.spec_from_file_location("gemini_ooda_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
gemini_ooda = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gemini_ooda
_spec.loader.exec_module(gemini_ooda)


@pytest.fixture
def isolated_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "gemini_ooda_cache"
    secrets_file = tmp_path / "secrets.env"
    monkeypatch.setattr(gemini_ooda, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(gemini_ooda, "COUNTER_PATH", cache_dir / "counters.json")
    monkeypatch.setattr(gemini_ooda, "SECRETS_FILE", secrets_file)
    monkeypatch.delenv("SAPPHIRE_GEMINI_LIVE", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    yield {"cache_dir": cache_dir, "secrets": secrets_file}


def test_dry_run_default_emits_mock_without_live_call(isolated_cache):
    captured: list[dict[str, Any]] = []

    def fake_sdk(*args, **kwargs):
        captured.append({"args": args, "kwargs": kwargs})
        return {"text": "{}", "total_tokens": 1}

    result = gemini_ooda.synthesize(
        topic="Crypto regime shift",
        context="BTC up, OI rising",
        mode="dry-run",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )
    assert captured == []
    assert result["metadata"]["mode_requested"] == "dry-run"
    assert result["metadata"]["mode_actual"] == "dry-run"
    assert result["metadata"]["cached"] is False
    assert "observe" in result["ooda"]
    assert result["ooda"].get("_mock_reason") == "dry-run"


def test_live_mode_requires_explicit_env_flag(isolated_cache, monkeypatch):
    monkeypatch.delenv("SAPPHIRE_GEMINI_LIVE", raising=False)

    def fake_sdk(*args, **kwargs):
        raise AssertionError("live SDK should not be called when env flag is missing")

    result = gemini_ooda.synthesize(
        topic="Vertex live readiness",
        context="just a probe",
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )
    assert result["metadata"]["mode_actual"] == "dry-run-blocked-by-env"


def test_sensitive_input_is_blocked_to_safety_mock(isolated_cache, monkeypatch):
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")

    def fake_sdk(*args, **kwargs):
        raise AssertionError("sensitive input should never reach the live SDK")

    result = gemini_ooda.synthesize(
        topic="Customer PIN is 4832 — should be redacted",
        context="THO customer name: Smith",
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )
    assert result["metadata"]["mode_actual"] == "dry-run-safety"
    assert result["metadata"]["sensitivity"]["sensitive"] is True


def test_live_path_uses_sdk_seam_and_caches(isolated_cache, monkeypatch):
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")

    payload = json.dumps(
        {
            "observe": "Regime is shifting bullish.",
            "orient": "Funding flat, OI up 3%.",
            "decide": "Stay in paper mode; raise alert thresholds.",
            "act": ["Increase dashboard polling.", "Add Telegram alert dry-run."],
        }
    )
    calls: list[dict[str, Any]] = []

    def fake_sdk(prompt: str, *, model: str, max_output_tokens: int, api_key: str):
        calls.append({"model": model, "max_output_tokens": max_output_tokens})
        assert api_key == "sk-test-key"
        return {"text": payload, "prompt_tokens": 42, "output_tokens": 64, "total_tokens": 106}

    first = gemini_ooda.synthesize(
        topic="Market regime",
        context="OI up 3% on BTC",
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )
    assert first["metadata"]["mode_actual"] == "live"
    assert first["ooda"]["observe"].startswith("Regime is shifting")
    assert first["metadata"]["tokens"]["total_tokens"] == 106
    assert len(calls) == 1

    # Second call with the same payload should hit the cache and not invoke the SDK.
    second = gemini_ooda.synthesize(
        topic="Market regime",
        context="OI up 3% on BTC",
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )
    assert second["metadata"]["cached"] is True
    assert len(calls) == 1


def test_rate_limit_blocks_excess_calls(isolated_cache, monkeypatch):
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")
    counters = {
        "calls": [9999999999.0] * gemini_ooda.MAX_CALLS_PER_HOUR,
        "month_tokens": 0,
        "month_key": "9999-12",
    }
    isolated_cache["cache_dir"].mkdir(parents=True, exist_ok=True)
    (isolated_cache["cache_dir"] / "counters.json").write_text(
        json.dumps(counters), encoding="utf-8"
    )

    def fake_sdk(*args, **kwargs):
        raise AssertionError("rate-limited request should never reach the live SDK")

    result = gemini_ooda.synthesize(
        topic="Throttle probe",
        context=None,
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )
    assert result["metadata"]["mode_actual"] == "dry-run-rate-limited"
    assert "rate_limit" in (result["metadata"].get("rate_limit_reason") or "")


def test_cost_cap_blocks_when_month_budget_consumed(isolated_cache, monkeypatch):
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")
    counters = {
        "calls": [],
        "month_tokens": gemini_ooda.MAX_TOKENS_PER_MONTH,
        "month_key": gemini_ooda._now_utc().strftime("%Y-%m"),
    }
    isolated_cache["cache_dir"].mkdir(parents=True, exist_ok=True)
    (isolated_cache["cache_dir"] / "counters.json").write_text(
        json.dumps(counters), encoding="utf-8"
    )

    def fake_sdk(*args, **kwargs):
        raise AssertionError("cost-capped request should never reach the live SDK")

    result = gemini_ooda.synthesize(
        topic="Cost cap probe",
        context=None,
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )
    assert result["metadata"]["mode_actual"] == "dry-run-rate-limited"
    assert "cost_cap" in (result["metadata"].get("rate_limit_reason") or "")


def test_unknown_model_returns_error(isolated_cache):
    result = gemini_ooda.synthesize(
        topic="Anything",
        context=None,
        mode="dry-run",
        model="bogus-model",
        max_output_tokens=128,
        ttl_seconds=600,
    )
    assert "error" in result
    assert "known_models" in result


def test_models_action_lists_known_models(isolated_cache):
    out = gemini_ooda.handle({"action": "models"})
    assert out["default"] == gemini_ooda.DEFAULT_MODEL
    assert "gemini-2.5-flash" in out["models"]


def test_status_action_does_not_contact_google(isolated_cache):
    state = gemini_ooda.handle({"action": "status"})
    assert state["live_env"] is False
    assert state["calls_last_hour"] == 0
    assert state["max_calls_per_hour"] == gemini_ooda.MAX_CALLS_PER_HOUR


def test_main_reads_stdin_and_writes_json(isolated_cache):
    stdin = io.StringIO(json.dumps({"action": "models"}))
    stdout = io.StringIO()
    rc = gemini_ooda.main(stdin, stdout)
    assert rc == 0
    parsed = json.loads(stdout.getvalue())
    assert parsed["default"] == gemini_ooda.DEFAULT_MODEL


def test_main_rejects_invalid_json(isolated_cache):
    stdin = io.StringIO("not-json")
    stdout = io.StringIO()
    rc = gemini_ooda.main(stdin, stdout)
    assert rc == 2
    assert "error" in json.loads(stdout.getvalue())


def test_main_rejects_non_object_payload(isolated_cache):
    stdin = io.StringIO("[1,2,3]")
    stdout = io.StringIO()
    rc = gemini_ooda.main(stdin, stdout)
    assert rc == 2
    assert "error" in json.loads(stdout.getvalue())


def test_unknown_action_returns_error(isolated_cache):
    out = gemini_ooda.handle({"action": "delete-everything"})
    assert "error" in out
    assert "synthesize" in out["valid_actions"]
