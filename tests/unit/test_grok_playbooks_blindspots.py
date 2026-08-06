from __future__ import annotations

from lib.grok.blindspots import blindspot_scoreboard
from lib.grok.playbooks import list_playbooks, playbook_summary


def test_playbooks_present():
    ids = list_playbooks()
    assert "axti_options" in ids
    assert "late_cycle_preservation" in ids
    assert playbook_summary()["count"] >= 5


def test_blindspots_scoreboard():
    s = blindspot_scoreboard()
    assert s["count"] >= 10
    assert "BS-GATE-WIRE" in s["open_p0"] or s["by_severity"].get("P0", 0) >= 1
