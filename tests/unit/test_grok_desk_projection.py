from __future__ import annotations

from lib.grok.desk_projection import build_desk_projection, markets_pulse, publisher_checklist


def test_desk_has_fresh_updated_at_and_no_wallet_keys():
    d = build_desk_projection(thesis="late cycle preservation", regime_label="mean_reverting")
    assert d["version"] == 1
    assert d["updated_at"]
    assert d["posture"] == "capital_preservation"
    assert d["epistemics"]["fresh"] is True
    # no wallet/balance keys in risk or top-level capital fields
    assert "wallet" not in d
    assert "balance" not in d
    assert "balance" not in d.get("risk", {})
    assert "realized_pnl_usd" not in d.get("epistemics", {}).get("learning", {})


def test_markets_pulse_unknown_safe():
    m = markets_pulse(events_per_min=100.0, feed_age_s=30.0, decision_gate="manual")
    assert m["status"] == "current"
    assert m["decision_gate"] == "manual"


def test_checklist_nonempty():
    assert len(publisher_checklist()) >= 5
