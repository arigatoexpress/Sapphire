from __future__ import annotations

from lib.grok.loop import DEFAULT_TASKS, tick


def test_tick_completes_policy():
    board = {"tasks": [dict(t) for t in DEFAULT_TASKS], "dynamic_tasks": []}
    out = tick(board, {"policy_tests_ok": True, "genome_seeded": True})
    statuses = {t["id"]: t["status"] for t in out["tasks"]}
    assert statuses["T-policy-kernel"] == "done"
    assert statuses["T-genome"] == "done"
    assert out["next_actions"]
    dyn_ids = {t["id"] for t in out["dynamic_tasks"]}
    assert "T-wire-policy-plant" in dyn_ids
