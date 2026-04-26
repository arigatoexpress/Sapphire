"""Tests for scripts/ops/record_kill_switch_baseline.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "record_kill_switch_baseline.py"
SPEC = importlib.util.spec_from_file_location("record_kill_switch_baseline", SCRIPT)
assert SPEC and SPEC.loader
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


def test_dry_run_does_not_write_audit(tmp_path):
    audit_path = tmp_path / "audit" / "kill_switch.jsonl"

    result = baseline.build_result(
        audit_path=audit_path,
        observed_active=False,
        apply=False,
    )

    assert result["ok"] is True
    assert result["applied"] is False
    assert result["dry_run"] is True
    assert result["observed_active"] is False
    assert result["reason_hash"]
    assert not audit_path.exists()


def test_apply_writes_operator_baseline_without_raw_secret_like_output(tmp_path):
    audit_path = tmp_path / "audit" / "kill_switch.jsonl"

    result = baseline.build_result(
        audit_path=audit_path,
        observed_active=True,
        apply=True,
    )
    rendered = baseline.render(result)
    record = json.loads(audit_path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["applied"] is True
    assert record["event_type"] == "kill_switch.operator_baseline"
    assert record["observed_active"] is True
    assert record["kind"] == "operator_baseline"
    assert "operator baseline recorded" not in rendered
    assert "reason_hash" not in record


def test_refuses_to_baseline_when_transition_exists_without_force(tmp_path):
    audit_path = tmp_path / "kill_switch.jsonl"
    audit_path.write_text(
        json.dumps(
            {
                "event_type": "kill_switch.activated",
                "kind": "activated",
                "timestamp": "2026-04-26T12:00:00+00:00",
                "reason": "halt",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = baseline.build_result(
        audit_path=audit_path,
        observed_active=False,
        apply=True,
    )

    assert result["ok"] is False
    assert result["exit_code"] == 78
    assert result["applied"] is False
    assert result["reason"] == "transition_events_already_present"
    assert audit_path.read_text(encoding="utf-8").count("\n") == 1
