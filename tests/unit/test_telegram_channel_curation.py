"""Tests for scripts/ops/telegram_channel_curation.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "telegram_channel_curation.py"
SPEC = importlib.util.spec_from_file_location("telegram_channel_curation", SCRIPT)
assert SPEC and SPEC.loader
curation = importlib.util.module_from_spec(SPEC)
sys.modules["telegram_channel_curation"] = curation
SPEC.loader.exec_module(curation)


def _clean_packet() -> dict:
    return {
        "schema_version": 1,
        "run_id": "unit-test",
        "candidates": [
            {
                "candidate_id": "@private_channel_alpha",
                "source_ref": "@private_channel_alpha",
                "category": "security",
                "operator_notes": "token=secret-value-123456 should not render",
                "sample_messages": [
                    {
                        "message_id": "m1",
                        "author_ref": "@analyst_alpha",
                        "published_at": "2026-04-28T10:00:00+00:00",
                        "text": (
                            "CVE-2026-1111 exploit confirmed against edge VPN devices; "
                            "vendor mitigation and indicators published."
                        ),
                    },
                    {
                        "message_id": "m2",
                        "author_ref": "@analyst_alpha",
                        "published_at": "2026-04-28T10:05:00+00:00",
                        "text": (
                            "Ransomware leak-site activity increased after the weekend; "
                            "attribution remains unconfirmed pending independent reports."
                        ),
                    },
                    {
                        "message_id": "m3",
                        "author_ref": "@analyst_beta",
                        "published_at": "2026-04-28T10:10:00+00:00",
                        "text": (
                            "Cloud provider outage update: API latency is elevated, "
                            "operators should monitor retry queues until recovery."
                        ),
                    },
                ],
            }
        ],
    }


def test_report_is_dry_run_and_paste_safe() -> None:
    report = curation.build_report(_clean_packet(), generated_at="2026-04-28T00:00:00+00:00")

    assert report["safety"] == {
        "telegram_contacted": False,
        "telegram_sends_enabled": False,
        "live_collection_enabled": False,
        "trading_critical_path_touched": False,
        "raw_handles_redacted": True,
    }
    blob = json.dumps(report)
    assert "@private_channel_alpha" not in blob
    assert "@analyst_alpha" not in blob
    assert "secret-value-123456" not in blob
    assert report["candidates"][0]["disabled_config_stub"]["enabled"] is False


def test_pump_samples_hold_candidate_for_review() -> None:
    packet = {
        "schema_version": 1,
        "run_id": "pump-test",
        "candidates": [
            {
                "candidate_id": "moon-room",
                "category": "crypto",
                "sample_messages": [
                    {
                        "message_id": f"pump-{index}",
                        "author_ref": f"bot-{index}",
                        "published_at": f"2026-04-28T10:0{index}:00+00:00",
                        "text": (
                            "TARGET COIN reveal now. Buy now for guaranteed 1000% profit. "
                            "Sniper bot execute in seconds."
                        ),
                    }
                    for index in range(4)
                ],
            }
        ],
    }

    report = curation.build_report(packet)
    candidate = report["candidates"][0]

    assert candidate["decision"] == "hold_bot_pump_review"
    rules = {finding["rule_id"] for finding in candidate["bot_pump_review"]["report"]["findings"]}
    assert "pump_language_with_bot_or_profit_claim" in rules
    assert "coordinated_pump_burst" in rules


def test_false_positive_dismissal_requires_all_evidence() -> None:
    packet = {
        "schema_version": 1,
        "run_id": "review-test",
        "candidates": [],
        "bot_pump_reviews": [
            {
                "review_id": "r1",
                "candidate_id": "markets-alpha",
                "finding": {
                    "rule_id": "coordinated_pump_burst",
                    "severity": "high",
                    "summary": "Burst looked coordinated.",
                },
                "operator_review": {
                    "decision": "dismiss_false_positive",
                    "evidence": {"no_profit_claim": True},
                },
            }
        ],
    }

    review = curation.build_report(packet)["bot_pump_false_positive_reviews"][0]

    assert review["state"] == "cannot_dismiss_yet"
    assert "independent_sources" in review["missing_requirements"]
    assert "sample_message_ids" in review["missing_requirements"]


def test_false_positive_dismissal_becomes_eligible_with_full_evidence() -> None:
    packet = {
        "schema_version": 1,
        "run_id": "review-test",
        "candidates": [],
        "bot_pump_reviews": [
            {
                "review_id": "r1",
                "candidate_id": "markets-alpha",
                "finding": {
                    "rule_id": "coordinated_pump_burst",
                    "severity": "high",
                    "summary": "Burst looked coordinated.",
                },
                "operator_review": {
                    "decision": "dismiss_false_positive",
                    "evidence": {
                        "independent_sources": ["source-a", "source-b"],
                        "no_profit_claim": True,
                        "no_coordination_burst": True,
                        "no_bot_execution_language": True,
                        "sample_message_ids": ["m1", "m2", "m3"],
                    },
                },
            }
        ],
    }

    review = curation.build_report(packet)["bot_pump_false_positive_reviews"][0]

    assert review["state"] == "eligible_for_false_positive_label"
    assert review["missing_requirements"] == []


def test_cli_writes_report(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    output = tmp_path / "report.json"
    packet.write_text(json.dumps(_clean_packet()), encoding="utf-8")

    assert curation.main(["--input", str(packet), "--output", str(output), "--pretty"]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "dry_run"
    assert report["summary"]["candidate_count"] == 1
