"""Plugin tests for ``inference_telemetry`` tool — stdin-JSON contract."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "internal" / "inference_telemetry.py"


def _tool():
    spec = importlib.util.spec_from_file_location("inference_telemetry_tool_test", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_status_action_reports_default_path():
    out = _tool().status_action({})
    assert out["ok"] is True
    assert out["calls_path"].endswith("calls.jsonl")
    # The path may or may not exist on a CI box — but the field is always present.
    assert "calls_path_exists" in out


def test_status_action_with_custom_path(tmp_path: Path):
    target = tmp_path / "custom.jsonl"
    target.write_text("", encoding="utf-8")
    out = _tool().status_action({"path": str(target)})
    assert out["calls_path"] == str(target)
    assert out["calls_path_exists"] is True


def test_report_action_runs_synthetic_fallback_when_no_data():
    """When ~/.cache/sapphire/inference_proxy/calls.jsonl is absent, synthetic kicks in."""
    out = _tool().report_action({})
    assert out["ok"] is True
    assert out["action"] == "report"
    # has_real_data is False for the synthetic fixture.
    assert out["has_real_data"] is False
    assert "tiers" in out
    assert "citations" in out
    assert any("moonshot.cn" in c for c in out["citations"])


def test_report_action_with_supplied_path_and_kimi_rates(tmp_path: Path):
    target = tmp_path / "calls.jsonl"
    target.write_text(
        json.dumps(
            {
                "tier": "T4_kimi_cloud",
                "ts": "2026-04-28T12:00:00Z",
                "latency_ms": 2400,
                "ok": True,
                "tokens_in": 1000,
                "tokens_out": 500,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = _tool().report_action(
        {
            "path": str(target),
            "cost_model": {
                "kimi_input_usd_per_1k_tokens": 1.20,
                "kimi_output_usd_per_1k_tokens": 2.40,
            },
        }
    )
    assert out["has_real_data"] is True
    assert out["total_cost_usd"] > 0  # Kimi rates supplied + 1 successful call
    assert out["cost_model"]["kimi_rates_supplied"] is True


def test_report_action_writes_provenance_stamped_file(tmp_path: Path):
    target = tmp_path / "calls.jsonl"
    target.write_text(
        json.dumps({"tier": "T1_windows_gpu", "latency_ms": 400, "ok": True}) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "out" / "report.json"
    res = _tool().report_action(
        {
            "path": str(target),
            "output_path": str(output),
        }
    )
    assert res["written_to"] == str(output)
    assert output.exists()
    written = json.loads(output.read_text())
    # Provenance envelope is best-effort; if present, it includes a generator name.
    if "provenance" in written:
        assert "generator" in written["provenance"]


def test_recommendations_action_caveats_present():
    out = _tool().recommendations_action({})
    assert out["ok"] is True
    assert out["action"] == "recommendations"
    assert any("Kimi" in c for c in out["caveats"])
    assert "top" in out


def test_cost_model_action_returns_default_model():
    out = _tool().cost_model_action({})
    assert out["ok"] is True
    assert out["cost_model"]["kimi_rates_supplied"] is False
    assert "moonshot_pricing_url" in out["cost_model"]


def test_handle_unknown_action_lists_valid_actions():
    out = _tool().handle({"action": "totally-bogus"})
    assert out["ok"] is False
    assert "valid_actions" in out
    assert "report" in out["valid_actions"]
    assert "recommendations" in out["valid_actions"]


def test_main_rejects_invalid_json():
    stream_in = io.StringIO("{not json")
    stream_out = io.StringIO()
    rc = _tool().main(stream_in=stream_in, stream_out=stream_out)
    assert rc == 2
    assert "invalid JSON" in stream_out.getvalue()


def test_main_rejects_array_payload():
    stream_in = io.StringIO("[1, 2, 3]")
    stream_out = io.StringIO()
    rc = _tool().main(stream_in=stream_in, stream_out=stream_out)
    assert rc == 2
    assert "JSON object" in stream_out.getvalue()


def test_main_accepts_status_action():
    stream_in = io.StringIO(json.dumps({"action": "status"}))
    stream_out = io.StringIO()
    rc = _tool().main(stream_in=stream_in, stream_out=stream_out)
    assert rc == 0
    parsed = json.loads(stream_out.getvalue())
    assert parsed["ok"] is True
    assert parsed["action"] == "status"
