from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lib.grok.windows import (
    P0_CHECKS,
    P1_CHECKS,
    REQUIRED_WINDOWS_PROXY_ALIASES,
    evaluate_windows_acceptance,
    evaluate_windows_acceptance_receipt,
)
from scripts.ops.production_readiness_sweep import WINDOWS_REQUIRED_MODELS

ROOT = Path(__file__).resolve().parents[2]
BOOT_ID = "DESKTOP-HFCK6U9@2026-08-10T21:54:33Z"


def _green_state() -> dict[str, bool]:
    return {key: True for key, _label in P0_CHECKS}


def _fresh_evidence(now: datetime) -> dict[str, dict[str, object]]:
    observed_at = (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    evidence = {key: {"status": "pass", "observed_at": observed_at} for key, _label in P0_CHECKS}
    evidence["ollama_aliases"].update(
        {
            "probe": "inference_proxy_alias_calls",
            "passed_aliases": sorted(WINDOWS_REQUIRED_MODELS),
        }
    )
    return evidence


def test_p0_blocks_arm():
    r = evaluate_windows_acceptance({})
    assert r["p0_ok"] is False
    assert r["arm_l2_allowed"] is False


def test_p0_green_allows_arm_only_with_fresh_boot_bound_evidence():
    now = datetime(2026, 8, 11, 14, 10, tzinfo=UTC)
    r = evaluate_windows_acceptance(
        _green_state(),
        evidence=_fresh_evidence(now),
        receipt_boot_id=BOOT_ID,
        current_boot_id=BOOT_ID,
        now=now,
    )
    assert r["p0_ok"] is True
    assert r["arm_l2_allowed"] is True
    assert r["p1_ok"] is False


def test_p0_rejects_stale_point_in_time_evidence():
    now = datetime(2026, 8, 11, 14, 10, tzinfo=UTC)
    evidence = _fresh_evidence(now)
    evidence["tailscale_up"]["observed_at"] = (
        (now - timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
    )

    result = evaluate_windows_acceptance(
        _green_state(),
        evidence=evidence,
        receipt_boot_id=BOOT_ID,
        current_boot_id=BOOT_ID,
        now=now,
    )

    assert result["p0_ok"] is False
    assert result["arm_l2_allowed"] is False
    tailscale = next(row for row in result["p0"] if row["id"] == "tailscale_up")
    assert tailscale["reason"] == "stale_evidence"


def test_p0_rejects_boot_mismatched_evidence():
    now = datetime(2026, 8, 11, 14, 10, tzinfo=UTC)

    result = evaluate_windows_acceptance(
        _green_state(),
        evidence=_fresh_evidence(now),
        receipt_boot_id=BOOT_ID,
        current_boot_id="DESKTOP-HFCK6U9@2026-08-11T14:09:00Z",
        now=now,
    )

    assert result["p0_ok"] is False
    assert result["arm_l2_allowed"] is False
    assert {row["reason"] for row in result["p0"]} == {"boot_mismatch"}


def test_p0_rejects_receipt_without_live_boot_readback():
    now = datetime(2026, 8, 11, 14, 10, tzinfo=UTC)

    result = evaluate_windows_acceptance(
        _green_state(),
        evidence=_fresh_evidence(now),
        receipt_boot_id=BOOT_ID,
        now=now,
    )

    assert result["p0_ok"] is False
    assert result["arm_l2_allowed"] is False
    assert {row["reason"] for row in result["p0"]} == {"boot_identity_unverified"}


def test_p0_rejects_inventory_only_alias_claim():
    now = datetime(2026, 8, 11, 14, 10, tzinfo=UTC)
    evidence = _fresh_evidence(now)
    evidence["ollama_aliases"] = {
        "status": "pass",
        "observed_at": (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
        "probe": "ollama_model_inventory",
        "passed_aliases": sorted(WINDOWS_REQUIRED_MODELS),
    }

    result = evaluate_windows_acceptance(
        _green_state(),
        evidence=evidence,
        receipt_boot_id=BOOT_ID,
        current_boot_id=BOOT_ID,
        now=now,
    )

    alias = next(row for row in result["p0"] if row["id"] == "ollama_aliases")
    assert alias["ok"] is False
    assert alias["reason"] == "proxy_alias_unverified"
    assert result["arm_l2_allowed"] is False


def test_checked_in_windows_acceptance_is_evidence_backed_and_fail_closed():
    payload = json.loads(
        (ROOT / "projects/grok/data/windows_acceptance.json").read_text(encoding="utf-8")
    )

    assert payload["schema_version"] == 3
    expected_checks = {key for key, _label in (*P0_CHECKS, *P1_CHECKS)}
    assert set(payload["evidence"]) == expected_checks
    assert payload["state"]["post_boot_report"] is True
    assert payload["state"]["ollama_aliases"] is False
    assert payload["evidence"]["ollama_aliases"]["probe"] == "ollama_model_inventory"
    assert payload["execution"]["arm_l2_allowed"] is False
    assert payload["execution"]["l2_armed"] is False

    result = evaluate_windows_acceptance_receipt(
        payload,
        current_boot_id=payload["source"]["boot_id"],
        now=datetime.fromisoformat(payload["observed_at"].replace("Z", "+00:00")),
    )
    assert result["p0_ok"] is False
    assert result["arm_l2_allowed"] is False


def test_windows_runbook_model_inventory_matches_readiness_contract():
    runbook = (ROOT / "docs/ops/windows-desktop-server-runbook.md").read_text(encoding="utf-8")

    assert set(WINDOWS_REQUIRED_MODELS) == REQUIRED_WINDOWS_PROXY_ALIASES
    for alias, model in WINDOWS_REQUIRED_MODELS.items():
        assert f"| `{alias}` | `{model}` |" in runbook
