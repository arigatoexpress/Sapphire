from __future__ import annotations

from lib.grok.free_reign_gate import GateRequest, batch_gate, gate_option_management, gate_order


def test_gate_blocks_dens_and_allows_defined_risk_option():
    deny = gate_order(
        GateRequest("BINGBONG", "buy", "rh_l2", "l2_token", 5.0)
    )
    assert deny.allowed is False
    assert deny.code == "DENS_BLOCK"

    allow = gate_order(
        GateRequest(
            "AXTI",
            "buy",
            "rh_agentic",
            "option",
            35.0,
            is_defined_risk_option=True,
        )
    )
    assert allow.allowed is True
    assert allow.arm == "TRADE"


def test_gate_option_management_scale_out():
    r = gate_option_management(entry_premium=0.7, mark_premium=2.2, remaining_qty=2)
    assert r.allowed is True
    assert r.code == "AXTI_SCALE_OUT"


def test_batch_gate():
    rs = batch_gate(
        [
            GateRequest("SONNY", "buy", "rh_l2", "l2_token", 1.0),
            GateRequest("ETH", "buy", "paper", "l2_token", 1.0),
        ]
    )
    assert rs[0].allowed is False
    assert rs[1].allowed is True
