"""Windows private DC acceptance evaluation (pure)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Ordered P0 ladder from WINDOWS-DATACENTER-MASTERPLAN
P0_CHECKS = (
    ("post_boot_report", "WIN-POST-BOOT report exists with crash hypothesis"),
    ("tailscale_up", "Tailscale connected"),
    ("ssh_stable", "SSH BatchMode probe ok"),
    ("ollama_aliases", "Required Ollama tier aliases present"),
    ("no_sleep", "Sleep/lock disabled for overnight"),
    ("free_reign_parity", "free-reign / dens / killswitch parity with Mac"),
    ("schtasks_inventory", "Scheduled tasks inventoried (not necessarily armed)"),
)

P1_CHECKS = (
    ("research_worker_smoke", "Research worker manual smoke produced paper_only manifest"),
    ("tv_agent_readonly", "TV agent read-only listening"),
    ("genome_seeded", "Genome lessons seeded (AXTI + dens)"),
)


def evaluate_windows_acceptance(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a state dict of boolean (or truthy) check results.

    ``state`` keys match P0/P1 check ids. Missing keys count as fail.
    """
    p0_results = []
    for key, label in P0_CHECKS:
        ok = bool(state.get(key))
        p0_results.append({"id": key, "label": label, "ok": ok})
    p1_results = []
    for key, label in P1_CHECKS:
        ok = bool(state.get(key))
        p1_results.append({"id": key, "label": label, "ok": ok})

    p0_ok = all(x["ok"] for x in p0_results)
    p1_ok = all(x["ok"] for x in p1_results)
    arm_allowed = p0_ok  # never ARM L2 workers before P0 green

    return {
        "p0_ok": p0_ok,
        "p1_ok": p1_ok,
        "arm_l2_allowed": arm_allowed,
        "p0": p0_results,
        "p1": p1_results,
        "failed_p0": [x["id"] for x in p0_results if not x["ok"]],
        "failed_p1": [x["id"] for x in p1_results if not x["ok"]],
    }
