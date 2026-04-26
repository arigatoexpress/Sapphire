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
    (audit_dir / "autonomy.jsonl").write_text(
        json.dumps(
            {
                "event_type": "autonomy.decision_evaluated",
                "ts": now,
                "actor": "decision_engine",
                "action": "evaluate_signal token=sample-token",
                "outcome": "allow",
                "risk": "financial_decision",
                "object_ref": "BTC:long password=sample-password",
                "metadata": {
                    "symbol": "BTC",
                    "raw_prompt": "do not render this prompt",
                    "api_key": "sample-key",
                },
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
    assert report["autonomy_audit"]["audit_exists"] is True
    assert report["autonomy_audit"]["schema"] == {
        "total_lines": 1,
        "valid_records": 1,
        "malformed_lines": 0,
        "missing_required_fields": {},
        "unredacted_secret_risk_records": 1,
    }
    assert report["autonomy_audit"]["event_counts"] == {"autonomy.decision_evaluated": 1}
    assert report["autonomy_audit"]["recent_events"][0]["object_ref_hash"]
    assert report["autonomy_audit"]["recent_events"][0]["action_hash"]
    assert "paper trade" not in serialized
    assert "password=sample-password" not in serialized
    assert "operator halt" not in serialized
    assert "sample-token" not in rendered
    assert "sample-key" not in serialized
    assert "do not render this prompt" not in serialized
    assert "BTC:long" not in serialized
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


def test_missing_autonomy_audit_reports_empty(tmp_path):
    summary = safety_status.summarize_autonomy_audit(tmp_path / "missing.jsonl")

    assert summary == {
        "audit_exists": False,
        "schema": {
            "total_lines": 0,
            "valid_records": 0,
            "malformed_lines": 0,
            "missing_required_fields": {},
            "unredacted_secret_risk_records": 0,
        },
        "event_counts": {},
        "actor_counts": {},
        "outcome_counts": {},
        "risk_counts": {},
        "recent_events": [],
    }


def test_autonomy_audit_summary_counts_and_hashes_sensitive_fields(tmp_path):
    audit_path = tmp_path / "autonomy.jsonl"
    audit_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "autonomy.alert_detected",
                        "ts": 1_775_000_000.0,
                        "actor": "decision_engine",
                        "action": "scan_alerts secret=sample-secret",
                        "outcome": "warning",
                        "risk": "market_alert",
                        "object_ref": "funding.extreme",
                        "metadata": {"kind": "funding", "payload": "raw payload"},
                    }
                ),
                "{not-json}",
                json.dumps(
                    {
                        "event_type": "autonomy.decision_evaluated",
                        "actor": "decision_engine",
                        "action": "evaluate_signal",
                        "outcome": "block",
                        "risk": "financial_decision",
                        "object_ref": "ETH:short",
                        "metadata": {"symbol": "ETH", "reason_count": 2},
                    }
                ),
            ]
        )
        + "\n"
    )

    summary = safety_status.summarize_autonomy_audit(audit_path, recent=5)
    rendered = safety_status.render_markdown(
        {
            "generated_at": "2026-04-26T00:00:00+00:00",
            "state_dir": str(tmp_path),
            "confirmation_firewall": {
                "pending_count": 0,
                "expired_pending_count": 0,
                "pending": [],
            },
            "kill_switch": {
                "audit_exists": False,
                "inferred_active": None,
                "last_transition": None,
                "recent_events": [],
            },
            "autonomy_audit": summary,
        }
    )
    serialized = json.dumps(summary)

    assert summary["event_counts"] == {
        "autonomy.alert_detected": 1,
        "autonomy.decision_evaluated": 1,
    }
    assert summary["schema"] == {
        "total_lines": 3,
        "valid_records": 2,
        "malformed_lines": 1,
        "missing_required_fields": {"ts": 1},
        "unredacted_secret_risk_records": 1,
    }
    assert summary["actor_counts"] == {"decision_engine": 2}
    assert summary["risk_counts"] == {"financial_decision": 1, "market_alert": 1}
    assert summary["recent_events"][0]["action_hash"]
    assert summary["recent_events"][0]["object_ref_hash"]
    assert summary["recent_events"][0]["metadata_keys"] == ["kind", "payload"]
    assert "sample-secret" not in serialized
    assert "raw payload" not in serialized
    assert "funding.extreme" not in rendered
    assert "ETH:short" not in rendered
    assert "1 malformed" in rendered


def test_json_mode_outputs_combined_report(tmp_path, capsys):
    state_dir = tmp_path / ".sapphire"
    state_dir.mkdir()

    assert safety_status.main(["--state-dir", str(state_dir), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["confirmation_firewall"]["pending_count"] == 0
    assert output["kill_switch"]["inferred_active"] is None
    assert output["autonomy_audit"]["audit_exists"] is False
