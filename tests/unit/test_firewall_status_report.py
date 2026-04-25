"""Tests for scripts/ops/firewall_status_report.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "firewall_status_report.py"
SPEC = importlib.util.spec_from_file_location("firewall_status_report", SCRIPT)
assert SPEC and SPEC.loader
firewall_status = importlib.util.module_from_spec(SPEC)
sys.modules["firewall_status_report"] = firewall_status
SPEC.loader.exec_module(firewall_status)


def test_report_omits_pending_action_and_details(tmp_path):
    state_dir = tmp_path / ".sapphire"
    pending_dir = state_dir / "pending_confirmations"
    pending_dir.mkdir(parents=True)
    now = time.time()
    (pending_dir / "ABC12345.json").write_text(
        json.dumps(
            {
                "code": "ABC12345",
                "risk": "financial",
                "status": "pending",
                "action": "paper trade token=sample-token",
                "details": "secret=sample-secret",
                "created": now - 5,
                "expires": now + 60,
            }
        )
    )

    report = firewall_status.build_report(state_dir=state_dir, now=now)
    rendered = firewall_status.render_markdown(report)

    assert report["pending_count"] == 1
    assert report["pending"][0]["code"] == "ABC12345"
    assert "paper trade" not in json.dumps(report)
    assert "sample-token" not in rendered
    assert "sample-secret" not in rendered


def test_report_counts_expired_pending_without_rendering_details(tmp_path):
    state_dir = tmp_path / ".sapphire"
    pending_dir = state_dir / "pending_confirmations"
    pending_dir.mkdir(parents=True)
    now = time.time()
    (pending_dir / "OLD12345.json").write_text(
        json.dumps(
            {
                "code": "OLD12345",
                "risk": "financial",
                "status": "pending",
                "action": "live trade should not render",
                "details": "password=sample-password",
                "created": now - 600,
                "expires": now - 300,
            }
        )
    )

    report = firewall_status.build_report(state_dir=state_dir, now=now)

    assert report["pending_count"] == 0
    assert report["expired_pending_count"] == 1
    assert "live trade" not in json.dumps(report)
    assert "sample-password" not in json.dumps(report)


def test_recent_audit_keeps_safe_fields_only(tmp_path):
    state_dir = tmp_path / ".sapphire"
    audit_dir = state_dir / "audit"
    audit_dir.mkdir(parents=True)
    audit_path = audit_dir / "confirmation_firewall.jsonl"
    audit_path.write_text(
        json.dumps(
            {
                "event_type": "confirmation.pending_created",
                "risk": "financial",
                "status": "pending",
                "code": "ABC12345",
                "action": "paper trade token=sample-token",
                "details_len": 99,
                "ts": 1_775_000_000.0,
            }
        )
        + "\n"
    )

    report = firewall_status.build_report(state_dir=state_dir, recent=5)
    rendered = firewall_status.render_markdown(report)

    assert report["recent_audit"][0]["event_type"] == "confirmation.pending_created"
    assert report["recent_audit"][0]["code"] == "ABC12345"
    assert "paper trade" not in json.dumps(report)
    assert "sample-token" not in rendered


def test_json_mode_outputs_report(tmp_path, capsys):
    state_dir = tmp_path / ".sapphire"
    state_dir.mkdir()

    assert firewall_status.main(["--state-dir", str(state_dir), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["pending_count"] == 0
    assert output["expired_pending_count"] == 0
