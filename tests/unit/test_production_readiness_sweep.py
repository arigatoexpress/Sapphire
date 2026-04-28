"""Tests for the production readiness sweep."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "production_readiness_sweep.py"

SPEC = importlib.util.spec_from_file_location("production_readiness_sweep", SCRIPT)
assert SPEC and SPEC.loader
sweep = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sweep
SPEC.loader.exec_module(sweep)


def test_parse_json_from_mixed_output_handles_cli_warnings() -> None:
    output = 'Warning: terminal\n{"response": "SAPPHIRE_GEMINI_PROBE_OK"}\n'

    assert sweep.parse_json_from_mixed_output(output) == {
        "response": "SAPPHIRE_GEMINI_PROBE_OK"
    }


def test_gemini_live_probe_uses_vertex_without_tools(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 20,
        env: dict[str, str] | None = None,
    ) -> sweep.RunResult:
        del cwd, timeout
        assert env is not None
        calls.append((cmd, env))
        return sweep.RunResult(
            0,
            """
            Warning: terminal
            {
              "response": "SAPPHIRE_GEMINI_PROBE_OK",
              "stats": {
                "models": {
                  "gemini-2.5-flash": {
                    "tokens": {"total": 42}
                  }
                },
                "tools": {"totalCalls": 0}
              }
            }
            """,
            "",
            123,
        )

    monkeypatch.setattr(sweep, "run", fake_run)

    checks = sweep.probe_gemini_live(
        argparse.Namespace(
            project="tho-ai-agent",
            region="us-central1",
            gemini_model="gemini-2.5-flash",
        )
    )

    assert checks[0].status == "PASS"
    assert "total_tokens=42" in checks[0].evidence
    assert calls[0][0][:2] == ["gemini", "--skip-trust"]
    assert calls[0][1]["GOOGLE_GENAI_USE_VERTEXAI"] == "true"
    assert calls[0][1]["GOOGLE_CLOUD_PROJECT"] == "tho-ai-agent"


def test_gemini_probe_converts_google_manual_gate_to_pass() -> None:
    google_gate = sweep.Check(
        "gcp",
        "gate_gemini_api_or_vertex_live_calls",
        "WARN",
        "manual_gate",
    )
    probe = sweep.Check("gemini", "vertex_live_probe", "PASS", "model=gemini-2.5-flash")

    sweep.apply_gemini_probe_to_google_gate([google_gate, probe], [probe])

    assert google_gate.status == "PASS"
    assert "Vertex Gemini live probe succeeded" in google_gate.evidence


class _FakeHTTPResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self, _limit: int) -> bytes:
        return self._body


def test_inference_health_warns_on_degraded_tiers(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "endpoints": {
                    "windows-gpu": "healthy",
                    "pi-rari1": "failed",
                    "mac-local": "healthy",
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.inference_proxy_health_check()

    assert check.status == "WARN"
    assert "status=ok" in check.evidence
    assert "degraded_tiers=pi-rari1" in check.evidence


def test_inference_health_passes_when_all_tiers_healthy(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "endpoints": {
                    "windows-gpu": "healthy",
                    "mac-local": "healthy",
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.inference_proxy_health_check()

    assert check.status == "PASS"
    assert "degraded_tiers" not in check.evidence
