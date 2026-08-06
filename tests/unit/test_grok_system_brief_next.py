from __future__ import annotations

from lib.grok.system_brief import build_system_brief


def test_brief_reflects_plant_wires():
    b = build_system_brief()
    assert b["streamline"]["max"] == 8
    assert b["bridge"].get("gate_wired") is True
    assert b["bridge"].get("genome_wired") is True
    actions = " ".join(b["next_actions"])
    assert "wire gate_order into free-reign" not in actions
    assert "reload rh-executor" in actions or "gate live" in actions
