from __future__ import annotations

import json
from pathlib import Path

from lib.grok.windows import P0_CHECKS, P1_CHECKS, evaluate_windows_acceptance
from scripts.ops.production_readiness_sweep import WINDOWS_REQUIRED_MODELS

ROOT = Path(__file__).resolve().parents[2]


def test_p0_blocks_arm():
    r = evaluate_windows_acceptance({})
    assert r["p0_ok"] is False
    assert r["arm_l2_allowed"] is False


def test_p0_green_allows_arm():
    state = {
        "post_boot_report": True,
        "tailscale_up": True,
        "ssh_stable": True,
        "ollama_aliases": True,
        "no_sleep": True,
        "free_reign_parity": True,
        "schtasks_inventory": True,
    }
    r = evaluate_windows_acceptance(state)
    assert r["p0_ok"] is True
    assert r["arm_l2_allowed"] is True
    assert r["p1_ok"] is False


def test_checked_in_windows_acceptance_is_evidence_backed_and_fail_closed():
    payload = json.loads(
        (ROOT / "projects/grok/data/windows_acceptance.json").read_text(encoding="utf-8")
    )

    assert payload["schema_version"] >= 2
    expected_checks = {key for key, _label in (*P0_CHECKS, *P1_CHECKS)}
    assert set(payload["evidence"]) == expected_checks
    assert payload["state"]["post_boot_report"] is True
    assert payload["execution"]["l2_armed"] is False

    result = evaluate_windows_acceptance(payload["state"])
    assert result["p0_ok"] is False
    assert result["arm_l2_allowed"] is False


def test_windows_runbook_model_inventory_matches_readiness_contract():
    runbook = (ROOT / "docs/ops/windows-desktop-server-runbook.md").read_text(encoding="utf-8")

    for alias, model in WINDOWS_REQUIRED_MODELS.items():
        assert f"| `{alias}` | `{model}` |" in runbook
