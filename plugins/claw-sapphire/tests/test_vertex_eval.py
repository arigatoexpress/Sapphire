"""Tests for the Sapphire Vertex/Gemini eval harness plugin tool.

Covers:
- prompt-set + status actions never contact Google or the local mesh
- the eval action's dry-run path produces a stable rubric without calling SDKs
- live mode is gated by ``SAPPHIRE_GEMINI_LIVE`` plus a key
- sensitive prompts are removed from the live batch
- compare() runs all three generators and emits deltas
- caps refuse over-large prompt sets and over-large output token requests
- the stdin JSON entry point matches the canonical Sapphire tool contract
- run artifacts get a provenance envelope plus a sidecar file
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
INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "vertex_eval.py"

_spec = importlib.util.spec_from_file_location("vertex_eval_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
vertex_eval = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = vertex_eval
_spec.loader.exec_module(vertex_eval)


_HIGH_QUALITY_PAYLOAD = json.dumps(
    {
        "observe": "BTC funding 0.005% with OI up 4.1% on perpetuals.",
        "orient": "Sapphire posture FLAT 40% USD; see [BTC](https://x).",
        "decide": "Hold paper book; raise alert thresholds 50 bps.",
        "act": [
            "Monitor open interest 4h reading.",
            "Run signal scanner against BTC perp.",
            "Update dashboard polling to 5 second cadence.",
        ],
    }
)


def _high_quality_local(*_args, **_kwargs):
    return {
        "text": _HIGH_QUALITY_PAYLOAD,
        "prompt_tokens": 12,
        "output_tokens": 24,
        "total_tokens": 36,
    }


def _high_quality_sdk(*_args, **_kwargs):
    return {
        "text": _HIGH_QUALITY_PAYLOAD,
        "prompt_tokens": 50,
        "output_tokens": 80,
        "total_tokens": 130,
    }


@pytest.fixture
def isolated_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "vertex_eval_cache"
    runs_dir = cache_dir / "runs"
    secrets_file = tmp_path / "secrets.env"
    monkeypatch.setattr(vertex_eval, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(vertex_eval, "COUNTER_PATH", cache_dir / "counters.json")
    monkeypatch.setattr(vertex_eval, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(vertex_eval, "LAST_RUN_PATH", cache_dir / "last_run.json")
    monkeypatch.setattr(vertex_eval, "SECRETS_FILE", secrets_file)
    monkeypatch.delenv("SAPPHIRE_GEMINI_LIVE", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    yield {"cache_dir": cache_dir, "runs_dir": runs_dir, "secrets": secrets_file}


def test_prompt_set_action_lists_canonical_sets(isolated_cache):
    out = vertex_eval.handle({"action": "prompt-set"})
    assert out["total_prompts"] == 9
    assert out["prompts_per_run_hard"] == vertex_eval.EVAL_PROMPTS_PER_RUN_HARD
    names = [s["name"] for s in out["sets"]]
    assert names == [
        "crypto-regime-shift",
        "vote-monitor-context",
        "threat-intel-summary",
        "sovereign-thesis-synthesis",
    ]


def test_status_action_never_contacts_google(isolated_cache):
    state = vertex_eval.handle({"action": "status"})
    assert state["live_env"] is False
    assert state["calls_last_hour"] == 0
    assert state["max_calls_per_hour"] == vertex_eval.MAX_CALLS_PER_HOUR
    assert state["last_run"] is None


def test_eval_dry_run_default_emits_baseline_rubric(isolated_cache):
    captured: list[Any] = []

    def fake_sdk(*args, **kwargs):
        captured.append(("sdk", args, kwargs))
        raise AssertionError("dry-run path must not call the live SDK")

    result = vertex_eval.evaluate(
        set_name="crypto-regime-shift",
        mode="dry-run",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        sdk_call=fake_sdk,
    )
    assert captured == []
    assert result["metadata"]["mode_actual"] == "dry-run"
    assert result["metadata"]["prompt_count"] == 3
    sections = {s["generator"] for s in result["generators"]}
    assert sections == {"dry-run"}
    aggregate = result["generators"][0]["aggregate"]
    assert aggregate["n"] == 3
    assert aggregate["structural_validity_mean"] == 1.0
    assert "provenance" in result
    # The run artifact must be persisted with a sidecar envelope.
    all_jsons = list(isolated_cache["runs_dir"].glob("*.json"))
    artifacts = [p for p in all_jsons if not p.name.endswith(".envelope.json")]
    sidecars = [p for p in all_jsons if p.name.endswith(".envelope.json")]
    assert len(artifacts) == 1
    assert len(sidecars) == 1


def test_eval_live_requires_env_flag(isolated_cache, monkeypatch):
    monkeypatch.delenv("SAPPHIRE_GEMINI_LIVE", raising=False)

    def fake_sdk(*args, **kwargs):
        raise AssertionError("live SDK should not be called when the env flag is missing")

    result = vertex_eval.evaluate(
        set_name="crypto-regime-shift",
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=128,
        sdk_call=fake_sdk,
    )
    assert result["metadata"]["mode_actual"] == "dry-run-blocked-by-env"
    assert {s["generator"] for s in result["generators"]} == {"dry-run"}


def test_eval_live_runs_when_gate_open(isolated_cache, monkeypatch):
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")
    calls: list[dict[str, Any]] = []

    def fake_sdk(prompt: str, *, model: str, max_output_tokens: int, api_key: str):
        calls.append(
            {"prompt_chars": len(prompt), "model": model, "max_output_tokens": max_output_tokens}
        )
        assert api_key == "sk-test-key"
        return _high_quality_sdk()

    result = vertex_eval.evaluate(
        set_name="crypto-regime-shift",
        mode="live",
        model="gemini-2.5-flash",
        max_output_tokens=256,
        sdk_call=fake_sdk,
    )
    assert result["metadata"]["mode_actual"] == "live"
    assert len(calls) == 3  # one per prompt in the set
    sections = {s["generator"] for s in result["generators"]}
    assert sections == {"dry-run", "gemini-live"}
    live = next(s for s in result["generators"] if s["generator"] == "gemini-live")
    assert live["aggregate"]["tokens_used_total"] == 130 * 3


def test_eval_live_skips_sensitive_prompts(isolated_cache, monkeypatch):
    """A sensitive case anywhere in the set keeps the live path closed."""
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")
    fake_set = "test-sensitive"

    sensitive_case = vertex_eval.PromptCase(
        set_name=fake_set,
        prompt_id=f"{fake_set}-01",
        topic="Customer PIN is 4832",
        context="Sensitive THO context",
    )
    safe_case = vertex_eval.PromptCase(
        set_name=fake_set,
        prompt_id=f"{fake_set}-02",
        topic="BTC funding read",
        context="OI up 3% on Binance perpetuals",
    )

    monkeypatch.setitem(
        vertex_eval.EVAL_PROMPT_SETS, fake_set, (sensitive_case, safe_case)
    )

    def fake_sdk(prompt: str, *, model: str, max_output_tokens: int, api_key: str):
        return _high_quality_sdk()

    result = vertex_eval.evaluate(
        set_name=fake_set,
        mode="live",
        max_output_tokens=128,
        sdk_call=fake_sdk,
    )
    assert result["metadata"]["mode_actual"] == "dry-run-safety"
    assert any(c["prompt_id"] == sensitive_case.prompt_id for c in result["metadata"][
        "sensitive_cases"
    ])
    sections = {s["generator"] for s in result["generators"]}
    assert sections == {"dry-run"}


def test_eval_caps_breach_blocks_oversized_output_tokens(isolated_cache):
    result = vertex_eval.evaluate(
        set_name="crypto-regime-shift",
        mode="dry-run",
        max_output_tokens=vertex_eval.MAX_OUTPUT_TOKENS_HARD + 1,
    )
    # ``evaluate`` clamps to the hard cap so this should still succeed.
    assert "error" not in result
    assert result["metadata"]["max_output_tokens"] == vertex_eval.MAX_OUTPUT_TOKENS_HARD


def test_eval_unknown_prompt_set_returns_error(isolated_cache):
    result = vertex_eval.evaluate(set_name="bogus-set")
    assert "error" in result
    assert "unknown_prompt_set" in result["error"]


def test_compare_reports_all_three_generators_in_dry_run(isolated_cache):
    result = vertex_eval.compare(
        set_name="vote-monitor-context",
        mode="dry-run",
        max_output_tokens=128,
        local_call=_high_quality_local,
    )
    sections = {s["generator"] for s in result["generators"]}
    assert sections == {"dry-run", "local-mesh"}
    assert "local_minus_dry" in result["deltas"]
    local = next(s for s in result["generators"] if s["generator"] == "local-mesh")
    assert local["aggregate"]["n"] == 2
    assert local["aggregate"]["structural_validity_mean"] == 1.0


def test_compare_includes_live_section_when_gated(isolated_cache, monkeypatch):
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")
    result = vertex_eval.compare(
        set_name="threat-intel-summary",
        mode="live",
        max_output_tokens=128,
        sdk_call=_high_quality_sdk,
        local_call=_high_quality_local,
    )
    sections = {s["generator"] for s in result["generators"]}
    assert sections == {"dry-run", "local-mesh", "gemini-live"}
    assert "live_minus_local" in result["deltas"]
    assert "live_minus_dry" in result["deltas"]


def test_compare_local_call_error_falls_back_to_mock(isolated_cache):
    def broken_local(*_args, **_kwargs):
        return {"text": "", "error": "URLError", "total_tokens": 0}

    result = vertex_eval.compare(
        set_name="vote-monitor-context",
        mode="dry-run",
        max_output_tokens=128,
        local_call=broken_local,
    )
    local = next(s for s in result["generators"] if s["generator"] == "local-mesh")
    assert all(
        record["error"] and record["error"].startswith("local_error:")
        for record in local["per_prompt"]
    )


def test_eval_rate_limit_falls_back_to_mock_per_prompt(isolated_cache, monkeypatch):
    isolated_cache["secrets"].write_text("GEMINI_API_KEY=sk-test-key\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")
    isolated_cache["cache_dir"].mkdir(parents=True, exist_ok=True)
    counters = {
        "calls": [9999999999.0] * vertex_eval.MAX_CALLS_PER_HOUR,
        "month_tokens": 0,
        "month_key": "9999-12",
        "runs": 0,
    }
    (isolated_cache["cache_dir"] / "counters.json").write_text(
        json.dumps(counters), encoding="utf-8"
    )

    def fake_sdk(*args, **kwargs):
        raise AssertionError("rate-limited request must not reach the SDK")

    result = vertex_eval.evaluate(
        set_name="vote-monitor-context",
        mode="live",
        max_output_tokens=128,
        sdk_call=fake_sdk,
    )
    live = next(s for s in result["generators"] if s["generator"] == "gemini-live")
    for record in live["per_prompt"]:
        assert record["error"] and record["error"].startswith("rate_limit")


def test_main_reads_stdin_and_writes_json(isolated_cache):
    stdin = io.StringIO(json.dumps({"action": "prompt-set"}))
    stdout = io.StringIO()
    rc = vertex_eval.main(stdin, stdout)
    assert rc == 0
    parsed = json.loads(stdout.getvalue())
    assert parsed["total_prompts"] == 9


def test_main_rejects_invalid_json(isolated_cache):
    stdin = io.StringIO("not-json")
    stdout = io.StringIO()
    rc = vertex_eval.main(stdin, stdout)
    assert rc == 2
    assert "error" in json.loads(stdout.getvalue())


def test_main_rejects_non_object_payload(isolated_cache):
    stdin = io.StringIO("[1,2,3]")
    stdout = io.StringIO()
    rc = vertex_eval.main(stdin, stdout)
    assert rc == 2
    assert "error" in json.loads(stdout.getvalue())


def test_unknown_action_returns_error(isolated_cache):
    out = vertex_eval.handle({"action": "delete-everything"})
    assert "error" in out
    assert "eval" in out["valid_actions"]


def test_run_artifact_envelope_is_provenance_stamped(isolated_cache):
    """The persisted artifact carries a verified provenance envelope."""
    provenance_spec = importlib.util.spec_from_file_location(
        "sapphire_provenance_for_vertex_eval_test",
        ROOT / "lib" / "core" / "provenance.py",
    )
    assert provenance_spec is not None and provenance_spec.loader is not None
    provenance = importlib.util.module_from_spec(provenance_spec)
    sys.modules[provenance_spec.name] = provenance
    provenance_spec.loader.exec_module(provenance)
    verify = provenance.verify

    result = vertex_eval.evaluate(
        set_name="vote-monitor-context",
        mode="dry-run",
        max_output_tokens=128,
    )
    artifacts = sorted(isolated_cache["runs_dir"].glob("*.json"))
    artifact_files = [p for p in artifacts if not p.name.endswith(".envelope.json")]
    assert len(artifact_files) == 1
    saved = json.loads(artifact_files[0].read_text(encoding="utf-8"))
    assert verify(saved) is True
    assert saved["provenance"]["generator"] == "plugins.claw_sapphire.vertex_eval"
    assert saved["provenance"]["model"] == result["metadata"]["model"]
    sidecar = artifact_files[0].with_name(f"{artifact_files[0].name}.envelope.json")
    assert sidecar.exists()
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["provenance"]["generator"] == "plugins.claw_sapphire.vertex_eval"
