"""Tests for scripts/ops/archive_expired_confirmations.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "archive_expired_confirmations.py"
SPEC = importlib.util.spec_from_file_location("archive_expired_confirmations", SCRIPT)
assert SPEC and SPEC.loader
archiver = importlib.util.module_from_spec(SPEC)
sys.modules["archive_expired_confirmations"] = archiver
SPEC.loader.exec_module(archiver)


def test_dry_run_reports_expired_without_moving_or_rendering_payload(tmp_path):
    state_dir = tmp_path / ".sapphire"
    pending_dir = state_dir / "pending_confirmations"
    pending_dir.mkdir(parents=True)
    now = time.time()
    expired = pending_dir / "OLD12345.json"
    expired.write_text(
        json.dumps(
            {
                "code": "OLD12345",
                "risk": "financial",
                "status": "pending",
                "action": "trade token=sample-token",
                "details": "password=sample-password",
                "created": now - 600,
                "expires": now - 300,
            }
        )
    )

    report = archiver.archive_expired_confirmations(state_dir=state_dir, now=now)
    rendered = archiver.render_markdown(report)

    assert report["applied"] is False
    assert report["matched_count"] == 1
    assert report["archived_count"] == 0
    assert report["entries"][0]["code"] == "OLD12345"
    assert report["entries"][0]["seconds_expired"] == 300
    assert expired.exists()
    assert "sample-token" not in json.dumps(report)
    assert "sample-password" not in rendered
    assert "trade token" not in rendered


def test_apply_moves_only_expired_pending_files(tmp_path):
    state_dir = tmp_path / ".sapphire"
    pending_dir = state_dir / "pending_confirmations"
    archive_dir = state_dir / "archived"
    pending_dir.mkdir(parents=True)
    now = time.time()

    expired = pending_dir / "OLD12345.json"
    active = pending_dir / "NEW12345.json"
    expired.write_text(json.dumps({"code": "OLD12345", "expires": now - 1}))
    active.write_text(json.dumps({"code": "NEW12345", "expires": now + 300}))

    report = archiver.archive_expired_confirmations(
        state_dir=state_dir,
        archive_dir=archive_dir,
        apply=True,
        now=now,
    )

    assert report["applied"] is True
    assert report["matched_count"] == 1
    assert report["archived_count"] == 1
    assert not expired.exists()
    assert active.exists()
    assert (archive_dir / "OLD12345.json").exists()
    assert report["entries"][0]["destination_hash"]


def test_json_mode_outputs_report(tmp_path, capsys):
    state_dir = tmp_path / ".sapphire"
    state_dir.mkdir()

    assert archiver.main(["--state-dir", str(state_dir), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["matched_count"] == 0
    assert output["archived_count"] == 0
