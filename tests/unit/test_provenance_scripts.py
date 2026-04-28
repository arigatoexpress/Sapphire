from __future__ import annotations

import json
from pathlib import Path

from scripts.ops import provenance_backfill, provenance_verify


def test_backfill_dry_run_does_not_write_sidecar(tmp_path) -> None:
    artifact = tmp_path / "draft.md"
    artifact.write_text("hello", encoding="utf-8")

    report = provenance_backfill.build_report((tmp_path,), apply=False)

    assert report["sidecars_to_write"] == 1
    assert not Path(report["rows"][0]["sidecar"]).exists()


def test_backfill_apply_writes_and_verify_passes(tmp_path) -> None:
    artifact = tmp_path / "draft.md"
    artifact.write_text("hello", encoding="utf-8")

    backfill = provenance_backfill.build_report((tmp_path,), apply=True)
    verify = provenance_verify.build_report((tmp_path,), older_than_hours=0)

    assert backfill["sidecars_written"] == 1
    assert verify["ok"] is True
    assert verify["checked"] == 1


def test_verify_reports_missing_sidecar(tmp_path) -> None:
    artifact = tmp_path / "draft.md"
    artifact.write_text("hello", encoding="utf-8")

    report = provenance_verify.build_report((tmp_path,), older_than_hours=0)

    assert report["ok"] is False
    assert report["missing_or_invalid"] == 1
    assert report["rows"][0]["reason"] == "missing_sidecar"


def test_backfill_cli_requires_explicit_apply_gate(tmp_path, capsys) -> None:
    artifact = tmp_path / "draft.md"
    artifact.write_text("hello", encoding="utf-8")

    rc = provenance_backfill.main(["--root", str(tmp_path), "--apply", "--pretty"])

    assert rc == 64
    assert not Path(f"{artifact}.envelope.json").exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["sidecars_to_write"] == 1


def test_verify_cli_returns_nonzero_for_missing_sidecar(tmp_path, capsys) -> None:
    artifact = tmp_path / "draft.md"
    artifact.write_text("hello", encoding="utf-8")

    rc = provenance_verify.main(["--root", str(tmp_path), "--older-than-hours", "0", "--pretty"])

    assert rc == 20
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["missing_or_invalid"] == 1
    assert payload["rows"][0]["reason"] == "missing_sidecar"


def test_backfill_and_verify_cli_round_trip(tmp_path, capsys) -> None:
    artifact = tmp_path / "draft.md"
    artifact.write_text("hello", encoding="utf-8")

    backfill_rc = provenance_backfill.main(["--root", str(tmp_path), "--apply", "--i-mean-it"])
    backfill = json.loads(capsys.readouterr().out)
    verify_rc = provenance_verify.main(["--root", str(tmp_path), "--older-than-hours", "0"])
    verify = json.loads(capsys.readouterr().out)

    assert backfill_rc == 0
    assert backfill["sidecars_written"] == 1
    assert verify_rc == 0
    assert verify["ok"] is True
    assert verify["checked"] == 1
