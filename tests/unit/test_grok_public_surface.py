from __future__ import annotations

from lib.grok.public_surface import diagnose_public_payloads, public_operating_rules


def test_operating_rules_withhold_wallets():
    r = public_operating_rules()
    assert r["disclosure"]["wallets"] == "withheld"
    assert "BINGBONG" in r["permanent_dens_symbols"] or "SONNY" in r["permanent_dens_symbols"]


def test_diagnose_desk_stale():
    rep = diagnose_public_payloads(
        live={
            "status": "live",
            "summary": {"active_agents": 1},
            "desk": {"posture": "unknown", "execution": "unknown", "updated_at": "2020-01-01T00:00:00Z"},
            "markets": {"events_per_min": 100, "decision_gate": "unknown", "execution": "unknown"},
        },
        widgets={
            "gate": {"state": "unavailable"},
            "wallet": {"disclosure": "withheld"},
            "research": {"clips": []},
            "recent_signals": [],
        },
    )
    ids = {i["id"] for i in rep["issues"]}
    assert "DESK_STALE_EMPTY" in ids
    assert "WALLET_WITHHELD_OK" in ids
