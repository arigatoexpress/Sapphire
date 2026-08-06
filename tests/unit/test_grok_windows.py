from __future__ import annotations

from lib.grok.windows import evaluate_windows_acceptance


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
