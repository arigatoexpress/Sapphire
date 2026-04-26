"""Tests for scripts/ops/safety_status_report.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "safety_status_report.py"
SPEC = importlib.util.spec_from_file_location("safety_status_report", SCRIPT)
assert SPEC and SPEC.loader
safety_status = importlib.util.module_from_spec(SPEC)
sys.modules["safety_status_report"] = safety_status
SPEC.loader.exec_module(safety_status)


def test_combined_report_omits_raw_pending_and_kill_switch_details(tmp_path):
    state_dir = tmp_path / ".sapphire"
    pending_dir = state_dir / "pending_confirmations"
    audit_dir = state_dir / "audit"
    pending_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    now = time.time()

    (pending_dir / "ABC12345.json").write_text(
        json.dumps(
            {
                "code": "ABC12345",
                "risk": "financial",
                "status": "pending",
                "action": "paper trade token=sample-token",
                "details": "password=sample-password",
                "created": now - 5,
                "expires": now + 60,
            }
        )
    )
    (audit_dir / "kill_switch.jsonl").write_text(
        json.dumps(
            {
                "event_type": "kill_switch.activated",
                "kind": "activated",
                "timestamp": "2026-04-25T12:00:00+00:00",
                "reason": "operator halt because token=sample-token",
                "portfolio_value": 90_000,
                "drawdown_24h": 0.0525,
                "drawdown_total": 0.071,
            }
        )
        + "\n"
    )

    report = safety_status.build_report(state_dir=state_dir, now=now)
    rendered = safety_status.render_markdown(report)
    serialized = json.dumps(report)

    assert report["confirmation_firewall"]["pending_count"] == 1
    assert report["kill_switch"]["inferred_active"] is True
    assert report["kill_switch"]["last_transition"]["reason_hash"]
    assert report["kill_switch"]["last_transition"]["reason_chars"] > 0
    assert "paper trade" not in serialized
    assert "password=sample-password" not in serialized
    assert "operator halt" not in serialized
    assert "sample-token" not in rendered
    assert "90000" not in rendered


def test_kill_switch_inferred_inactive_from_last_transition(tmp_path):
    audit_path = tmp_path / "kill_switch.jsonl"
    audit_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "kill_switch.activated",
                        "kind": "activated",
                        "timestamp": "2026-04-25T12:00:00+00:00",
                        "reason": "halt",
                    }
                ),
                json.dumps(
                    {
                        "event_type": "kill_switch.deactivated",
                        "kind": "deactivated",
                        "timestamp": "2026-04-25T12:05:00+00:00",
                        "reason": "resume",
                    }
                ),
            ]
        )
        + "\n"
    )

    summary = safety_status.summarize_kill_switch(audit_path, recent=5)

    assert summary["audit_exists"] is True
    assert summary["inferred_active"] is False
    assert summary["last_transition"]["event_type"] == "kill_switch.deactivated"
    assert summary["event_counts"] == {
        "kill_switch.activated": 1,
        "kill_switch.deactivated": 1,
    }


def test_missing_kill_switch_audit_reports_unknown(tmp_path):
    summary = safety_status.summarize_kill_switch(tmp_path / "missing.jsonl")

    assert summary == {
        "audit_exists": False,
        "inferred_active": None,
        "last_transition": None,
        "event_counts": {},
        "recent_events": [],
    }


def test_json_mode_outputs_combined_report(tmp_path, capsys):
    state_dir = tmp_path / ".sapphire"
    state_dir.mkdir()

    assert safety_status.main(["--state-dir", str(state_dir), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["confirmation_firewall"]["pending_count"] == 0
    assert output["kill_switch"]["inferred_active"] is None
