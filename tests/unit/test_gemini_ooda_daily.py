"""Daily Gemini OODA dry-run wrapper tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ops" / "gemini_ooda_daily.py"
SPEC = importlib.util.spec_from_file_location("gemini_ooda_daily", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
gemini_ooda_daily = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gemini_ooda_daily
SPEC.loader.exec_module(gemini_ooda_daily)


def test_diff_packets_reports_additions_removals_and_mutations() -> None:
    yesterday = {
        "topic": "daily",
        "context_summary": {"totals": {"assets": 2}, "old": True},
        "tool_response": {"ooda": {"decide": "hold", "act": ["watch"]}},
    }
    today = {
        "topic": "daily",
        "context_summary": {"totals": {"assets": 3}},
        "tool_response": {"ooda": {"decide": "tighten", "observe": "coverage up"}},
    }

    diff = gemini_ooda_daily.diff_packets(today, yesterday)

    assert diff["available"] is True
    assert "context_summary.old" in diff["removed"]
    assert "tool_response.ooda.observe" in diff["added"]
    mutated = {row["key"]: row for row in diff["mutated"]}
    assert mutated["context_summary.totals.assets"]["before"] == "2"
    assert mutated["context_summary.totals.assets"]["after"] == "3"
    assert mutated["tool_response.ooda.decide"]["before"] == "hold"
    assert mutated["tool_response.ooda.decide"]["after"] == "tighten"


def test_run_daily_writes_packet_envelope_and_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        gemini_ooda_daily,
        "build_thesis_context",
        lambda: (
            "paste-safe context",
            {"top_assets": [{"symbol": "BTC", "relative_score": 99.0}], "totals": {"assets": 1}},
        ),
    )

    def fake_runner(cmd, **kwargs):
        request = json.loads(kwargs["input"])
        assert request["mode"] == "dry-run"
        assert kwargs["env"]["SAPPHIRE_GEMINI_LIVE"] == "0"
        assert cmd[0] == sys.executable
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "ooda": {
                        "observe": "offline",
                        "orient": "dry-run",
                        "decide": "write packet",
                        "act": ["check sidecar"],
                    },
                    "metadata": {"mode_actual": "dry-run"},
                }
            ),
            stderr="",
        )

    result = gemini_ooda_daily.run_daily(
        day="2026-04-28",
        out_dir=tmp_path / "gemini-ooda",
        events_path=tmp_path / "system_events.jsonl",
        runner=fake_runner,
    )

    assert result.packet_path.exists()
    assert result.envelope_path.exists()
    assert result.packet["date"] == "2026-04-28"
    assert result.packet["tool_response"]["metadata"]["mode_actual"] == "dry-run"
    assert "sapphire_gemini_live_env_forced_zero" in result.packet["safety"]["guards"]

    event = json.loads((tmp_path / "system_events.jsonl").read_text(encoding="utf-8"))
    assert event["type"] == "gemini_ooda_daily"
    assert event["priority"] == "p3"
    assert "priority:p3" in event["tags"]
    assert event["data"]["packet_path"].endswith("2026-04-28.json")
