from __future__ import annotations

from lib.grok.policy import OrderProposal, evaluate_proposal, evaluate_scale_out, is_dens_blocked


def test_dens_blocks_sonny_buy():
    d = evaluate_proposal(OrderProposal("SONNY", "buy", "rh_l2", "l2_token", 5.0))
    assert d.allow is False
    assert d.code == "DENS_BLOCK"


def test_dens_blocks_addr_prefix():
    blocked, why = is_dens_blocked("RANDOM", contract_address="0x9763deadbeef")
    assert blocked and "dens_addr" in why


def test_dust_no_rebuy():
    d = evaluate_proposal(OrderProposal("IBIT", "buy", "rh_agentic", "equity", 20.0))
    assert d.allow is False
    assert d.code in {"DUST_NO_REBUY", "OPTIONS_FIRST"}


def test_l2_notional_cap():
    d = evaluate_proposal(OrderProposal("ETH", "buy", "rh_l2", "l2_token", 25.0))
    assert d.allow is False
    assert d.code == "L2_NOTIONAL_CAP"


def test_l2_max_open():
    d = evaluate_proposal(
        OrderProposal("ETH", "buy", "rh_l2", "l2_token", 5.0, open_positions_on_rail=1)
    )
    assert d.allow is False
    assert d.code == "L2_MAX_OPEN"


def test_moss_requires_grant():
    d = evaluate_proposal(
        OrderProposal("MOSS", "buy", "moss", "l2_token", 1.0, moss_grant_hours_left=-1)
    )
    assert d.allow is False
    assert d.code == "MOSS_GRANT"


def test_paper_option_allow():
    d = evaluate_proposal(
        OrderProposal(
            "AXTI",
            "buy",
            "paper",
            "option",
            35.0,
            is_defined_risk_option=True,
        )
    )
    assert d.allow is True


def test_agentic_defined_risk_option_allow():
    d = evaluate_proposal(
        OrderProposal(
            "AXTI",
            "buy",
            "rh_agentic",
            "option",
            35.0,
            is_defined_risk_option=True,
        )
    )
    assert d.allow is True
    assert d.code == "ALLOW"


def test_axti_scale_out_and_sl():
    so = evaluate_scale_out(entry_premium=0.70, mark_premium=2.25, remaining_qty=2)
    assert so.allow is True
    assert so.code == "AXTI_SCALE_OUT"
    sl = evaluate_scale_out(entry_premium=1.0, mark_premium=0.5, remaining_qty=1)
    assert sl.allow is True
    assert sl.code == "AXTI_SL"


def test_sell_exit_allowed_even_if_dust():
    d = evaluate_proposal(OrderProposal("NVDA", "sell", "rh_agentic", "equity", 5.0))
    assert d.allow is True
