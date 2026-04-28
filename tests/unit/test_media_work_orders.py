"""Tests for offline media work-order generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.media.work_orders import (
    build_work_order,
    discover_drafts,
    generate_work_orders,
    write_work_order,
)


def _write_draft(root, stamp: str, kind: str, *, passed: bool = True):
    content = root / "data" / "content"
    drafts = content / "drafts"
    ready_x = content / "ready" / "x"
    ready_substack = content / "ready" / "substack"
    drafts.mkdir(parents=True, exist_ok=True)
    ready_x.mkdir(parents=True, exist_ok=True)
    ready_substack.mkdir(parents=True, exist_ok=True)

    x_path = ready_x / f"{stamp}_{kind}.jsonl"
    substack_path = ready_substack / f"{stamp}_{kind}.md"
    x_path.write_text(
        json.dumps({"index": 0, "text": f"{kind} thread opener with cited facts."}) + "\n"
    )
    substack_path.write_text(
        f"# {kind} title\n\nGenerated content for {kind}.\n\nInformational only.\n"
    )
    draft_path = drafts / f"{stamp}_{kind}.json"
    draft_path.write_text(
        json.dumps(
            {
                "published_at": f"2026-04-27T{stamp[-4:-2]}:{stamp[-2:]}:00",
                "renderings": {
                    "x": {
                        "path": f"data/content/ready/x/{stamp}_{kind}.jsonl",
                        "quality": {
                            "passed": passed,
                            "word_count": 12,
                            "citation_count": 1,
                            "evidence_coverage": 1.0,
                            "unsupported_claims": [],
                            "performance_claim_violations": [],
                            "reasons": [] if passed else ["unit-test failure"],
                        },
                    },
                    "substack": {
                        "path": f"data/content/ready/substack/{stamp}_{kind}.md",
                        "quality": {
                            "passed": True,
                            "word_count": 24,
                            "citation_count": 1,
                            "evidence_coverage": 1.0,
                            "unsupported_claims": [],
                            "performance_claim_violations": [],
                            "reasons": [],
                        },
                    },
                },
                "report": {
                    "kind": kind,
                    "title": f"Unit {kind}",
                    "generated_at": "2026-04-27T12:00:00+00:00",
                    "facts": {
                        "forecasts": [{"symbol": "BTC"}, {"symbol": "ETH"}],
                        "data_sources": ["data/trading_predictions.jsonl"],
                    },
                },
            }
        )
        + "\n"
    )
    return draft_path


def test_discover_drafts_latest_per_kind(tmp_path):
    content_root = tmp_path / "data" / "content"
    _write_draft(tmp_path, "20260427_0607", "market_pulse")
    latest = _write_draft(tmp_path, "20260427_0610", "market_pulse")
    weekly = _write_draft(tmp_path, "20260427_0609", "weekly_crypto_brief")

    selected = discover_drafts(content_root, latest=True)

    assert selected == [latest, weekly]


def test_build_work_order_from_draft_manifest(tmp_path):
    draft = _write_draft(tmp_path, "20260427_0607", "weekly_crypto_brief")

    order = build_work_order(
        draft,
        root=tmp_path,
        manifest_root=tmp_path / "data" / "media" / "manifests",
        created_at=datetime(2026, 4, 27, 13, 0, tzinfo=UTC),
    )

    assert order["schema_version"] == 1
    assert order["work_order_id"] == "20260427_media_work_order_20260427_0607_weekly_crypto_brief"
    assert order["dry_run"] is True
    assert order["report"]["kind"] == "weekly_crypto_brief"
    assert order["provenance_manifest_path"] == (
        "data/media/manifests/20260427_media_work_order_20260427_0607_weekly_crypto_brief.json"
    )
    assert order["report"]["summary"]["symbols"] == ["BTC", "ETH"]
    assert order["renderings"][0]["path"].startswith("data/content/ready/")
    assert order["deliverables"]["image_card"]["headline"] == "Unit weekly_crypto_brief"
    assert order["deliverables"]["voiceover"]["max_seconds"] == 30
    assert any("Do not add" in item for item in order["constraints"])


def test_write_work_order_creates_order_and_manifest(tmp_path):
    draft = _write_draft(tmp_path, "20260427_0607", "market_pulse")

    result = write_work_order(
        draft,
        root=tmp_path,
        output_root=tmp_path / "data" / "media" / "work_orders",
        manifest_root=tmp_path / "data" / "media" / "manifests",
        created_at=datetime(2026, 4, 27, 13, 0, tzinfo=UTC),
    )

    order_path = result["path"]
    assert order_path.is_file()
    assert result["manifest"]["outputs"][0]["path"] == (
        "data/media/work_orders/20260427_media_work_order_20260427_0607_market_pulse.json"
    )
    assert result["manifest"]["inputs"][0]["path"] == (
        "data/content/drafts/20260427_0607_market_pulse.json"
    )
    saved = json.loads(order_path.read_text())
    assert saved["work_order_path"] == result["work_order"]["work_order_path"]


def test_generate_work_orders_latest_selected_kinds(tmp_path):
    _write_draft(tmp_path, "20260427_0607", "market_pulse")
    _write_draft(tmp_path, "20260427_0609", "weekly_crypto_brief")

    results = generate_work_orders(
        content_root=tmp_path / "data" / "content",
        root=tmp_path,
        output_root=tmp_path / "data" / "media" / "work_orders",
        manifest_root=tmp_path / "data" / "media" / "manifests",
        kinds=["weekly_crypto_brief"],
        latest=True,
        created_at=datetime(2026, 4, 27, 13, 0, tzinfo=UTC),
    )

    assert len(results) == 1
    assert results[0]["work_order"]["report"]["kind"] == "weekly_crypto_brief"
