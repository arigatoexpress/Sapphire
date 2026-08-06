from __future__ import annotations

from lib.grok.system_brief import build_system_brief, critical_alpha, load_alpha, policy_smoke


def test_policy_smoke_ok():
    assert policy_smoke()["ok"] is True


def test_alpha_loads_and_critical():
    alpha = load_alpha()
    assert (alpha.get("itemCount") or len(alpha.get("items") or [])) >= 5
    crit = critical_alpha(alpha, limit=5)
    assert len(crit) >= 1
    assert crit[0].get("severity") in ("critical", "high", "medium", "low")


def test_build_brief_shape():
    b = build_system_brief()
    assert "streamline" in b
    assert b["policy_smoke"]["ok"] is True
    assert b["alpha_item_count"] >= 5
    assert b["bridge"]["export_count"] >= 5
    assert b["next_actions"]
