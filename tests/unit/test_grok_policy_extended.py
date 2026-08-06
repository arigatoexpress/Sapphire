from __future__ import annotations

from lib.grok.policy import OrderProposal, evaluate_proposal


def test_day_loss_halt():
    d = evaluate_proposal(
        OrderProposal("ETH", "buy", "paper", "l2_token", 1.0, day_realized_pnl_usd=-80)
    )
    assert d.code == "DAY_LOSS_HALT"


def test_axti_dte():
    d = evaluate_proposal(
        OrderProposal(
            "AXTI",
            "buy",
            "rh_agentic",
            "option",
            35.0,
            is_defined_risk_option=True,
            dte_days=45,
        )
    )
    assert d.code == "AXTI_DTE"


def test_hl_signing_gate():
    d = evaluate_proposal(OrderProposal("BTC", "buy", "hyperliquid", "perp", 10.0))
    assert d.code == "HL_SIGNING_GATE"


def test_regime_block_l2():
    d = evaluate_proposal(
        OrderProposal("ETH", "buy", "rh_l2", "l2_token", 5.0, regime="crisis")
    )
    assert d.code == "REGIME_BLOCK_L2"


def test_options_day_cap():
    d = evaluate_proposal(
        OrderProposal(
            "AXTI",
            "buy",
            "rh_agentic",
            "option",
            40.0,
            is_defined_risk_option=True,
            day_options_premium_usd=120.0,
            dte_days=7,
        )
    )
    assert d.code == "OPTIONS_DAY_CAP"


def test_no_trade_arm_on_rejection():
    d = evaluate_proposal(OrderProposal("SONNY", "buy", "rh_l2", "l2_token", 5.0))
    assert d.allow is False
    assert d.arm == "NO_TRADE"
    assert d.code == "DENS_BLOCK"
