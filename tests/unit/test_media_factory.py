"""Tests for the local dry-run media factory."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import pytest

from lib.media.__main__ import main as media_main
from lib.media.factory import (
    MediaFactorySafetyError,
    media_factory_status,
    run_media_factory,
    validate_work_order,
)


def _minimal_work_order(root):
    draft_path = root / "data" / "content" / "drafts" / "unit_market_pulse.json"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps({"report": {"kind": "market_pulse"}}) + "\n")

    work_order_id = "20260427_media_work_order_unit_market_pulse"
    work_order = {
        "schema_version": 1,
        "work_order_id": work_order_id,
        "created_at": "2026-04-27T13:00:00Z",
        "dry_run": True,
        "approval_status": "pending",
        "source_draft": "data/content/drafts/unit_market_pulse.json",
        "source_paths": ["data/content/drafts/unit_market_pulse.json"],
        "renderings": [],
        "constraints": ["Use only facts present in the source draft."],
        "report": {
            "kind": "market_pulse",
            "title": "Unit Market Pulse",
            "summary": {"symbols": ["BTC"], "forecast_count": 1, "data_sources": []},
        },
        "deliverables": {
            "image_card": {
                "format": "square 1:1 and vertical 9:16 variants",
                "headline": "Unit Market Pulse",
                "overlay_text": ["Unit Market Pulse", "BTC"],
                "alt_text": "Operational media card for Unit Market Pulse",
                "style": {
                    "palette": ["charcoal", "amber", "cool white"],
                    "avoid": ["fake charts"],
                },
            },
            "short_video": {
                "duration_seconds": 30,
                "storyboard": [{"scene": 1, "seconds": "0-6", "brief": "Open"}],
            },
            "voiceover": {
                "tone": "calm operator briefing",
                "script": "Unit voiceover script.",
                "max_seconds": 30,
            },
        },
    }
    work_order_path = root / "data" / "media" / "work_orders" / f"{work_order_id}.json"
    work_order_path.parent.mkdir(parents=True, exist_ok=True)
    work_order_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n")
    return work_order_path, work_order


def test_validate_work_order_rejects_live_and_publish_flags(tmp_path):
    _work_order_path, work_order = _minimal_work_order(tmp_path)
    work_order["dry_run"] = False
    work_order["approval_status"] = "approved"
    work_order["deliverables"]["short_video"]["telegram_enabled"] = True
    work_order["deliverables"]["voiceover"]["run_mode"] = "live"

    validation = validate_work_order(
        work_order,
        root=tmp_path,
        checked_at=datetime(2026, 4, 27, 13, 30, tzinfo=UTC),
    )

    assert validation["ok"] is False
    messages = {issue["message"] for issue in validation["errors"]}
    assert "work order must be dry_run=true" in messages
    assert "approval_status must remain pending" in messages
    assert "live, publishing, or Telegram flag must be false" in messages
    assert "live execution modes are not allowed" in messages


def test_run_media_factory_writes_readiness_artifacts_and_status(tmp_path):
    work_order_path, work_order = _minimal_work_order(tmp_path)
    run_root = tmp_path / "data" / "media" / "runs"

    summary = run_media_factory(
        work_order_path,
        root=tmp_path,
        run_root=run_root,
        created_at=datetime(2026, 4, 27, 14, 0, tzinfo=UTC),
    )

    run_dir = run_root / work_order["work_order_id"]
    assert summary["status"] == "ready"
    assert summary["dry_run"] is True
    assert summary["api_calls_made"] is False
    assert summary["telegram_sends_made"] is False
    assert summary["publish_actions_made"] is False
    assert (run_dir / "factory_run.json").is_file()
    assert (run_dir / "image" / "prompt.md").read_text() == (
        "# Image Readiness\n"
        "\n"
        "Headline: Unit Market Pulse\n"
        "Alt text: Operational media card for Unit Market Pulse\n"
        "Format: square 1:1 and vertical 9:16 variants\n"
        "\n"
        "Overlay text:\n"
        "- Unit Market Pulse\n"
        "- BTC\n"
        "\n"
        "Style:\n"
        "{\n"
        "  \"avoid\": [\n"
        "    \"fake charts\"\n"
        "  ],\n"
        "  \"palette\": [\n"
        "    \"charcoal\",\n"
        "    \"amber\",\n"
        "    \"cool white\"\n"
        "  ]\n"
        "}\n"
        "\n"
        "Safety: dry-run only; no image API call was made.\n"
    )

    audio = json.loads((run_dir / "audio" / "readiness.json").read_text())
    video = json.loads((run_dir / "video" / "storyboard.json").read_text())
    assert audio["script"] == "Unit voiceover script."
    assert audio["live_calls_allowed"] is False
    assert video["storyboard"] == [{"brief": "Open", "scene": 1, "seconds": "0-6"}]
    assert len(summary["outputs"]) == 6

    status = media_factory_status(run_root=run_root, root=tmp_path)
    assert status["count"] == 1
    assert status["runs"][0]["work_order_id"] == work_order["work_order_id"]
    assert status["runs"][0]["media_kinds"] == ["audio", "image", "video"]


def test_run_media_factory_refuses_unsafe_work_order(tmp_path):
    work_order_path, work_order = _minimal_work_order(tmp_path)
    work_order["publish"] = True
    work_order_path.write_text(json.dumps(work_order) + "\n")

    with pytest.raises(MediaFactorySafetyError) as exc:
        run_media_factory(work_order_path, root=tmp_path, run_root=tmp_path / "runs")

    assert exc.value.validation["ok"] is False
    assert not (tmp_path / "runs" / work_order["work_order_id"]).exists()


def test_media_cli_validate_run_and_status(tmp_path, monkeypatch, capsys):
    work_order_path, work_order = _minimal_work_order(tmp_path)
    run_root = tmp_path / "data" / "media" / "runs"
    work_order_root = tmp_path / "data" / "media" / "work_orders"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m lib.media",
            "validate",
            str(work_order_path),
            "--root",
            str(tmp_path),
            "--pretty",
        ],
    )
    assert media_main() == 0
    validation_summary = json.loads(capsys.readouterr().out)
    assert validation_summary["ok"] is True
    assert validation_summary["count"] == 1

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m lib.media",
            "run",
            "--root",
            str(tmp_path),
            "--work-order-root",
            str(work_order_root),
            "--run-root",
            str(run_root),
            "--limit",
            "1",
            "--pretty",
        ],
    )
    assert media_main() == 0
    run_summary = json.loads(capsys.readouterr().out)
    assert run_summary["ok"] is True
    assert run_summary["runs"][0]["work_order_id"] == work_order["work_order_id"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m lib.media",
            "status",
            "--root",
            str(tmp_path),
            "--run-root",
            str(run_root),
            "--work-order-id",
            work_order["work_order_id"],
            "--pretty",
        ],
    )
    assert media_main() == 0
    status_summary = json.loads(capsys.readouterr().out)
    assert status_summary["count"] == 1
    assert status_summary["runs"][0]["status"] == "ready"


def test_media_cli_accepts_work_order_option_alias(tmp_path, monkeypatch, capsys):
    work_order_path, work_order = _minimal_work_order(tmp_path)
    run_root = tmp_path / "data" / "media" / "runs"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m lib.media",
            "run",
            "--work-order",
            str(work_order_path),
            "--root",
            str(tmp_path),
            "--run-root",
            str(run_root),
            "--pretty",
        ],
    )

    assert media_main() == 0
    run_summary = json.loads(capsys.readouterr().out)
    assert run_summary["ok"] is True
    assert run_summary["runs"][0]["work_order_id"] == work_order["work_order_id"]
