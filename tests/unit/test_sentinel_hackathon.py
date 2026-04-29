from __future__ import annotations

from decimal import Decimal

from lib.hackathon.sentinel import (
    ROBINHOOD_CHAIN_ID,
    blocked_attempt,
    build_demo_state,
    default_attempt,
    default_mandate,
    evaluate_attempt,
    evaluate_from_payload,
)


def test_default_attempt_is_approved_and_testnet_only():
    decision = evaluate_attempt(default_attempt(), default_mandate())

    assert decision.approved is True
    assert decision.risk_flags == ()
    assert decision.chain_anchor["chain_id"] == ROBINHOOD_CHAIN_ID
    assert decision.chain_anchor["broadcast"] is False
    assert decision.payment_requirements.network == "base-sepolia"
    assert decision.payment_requirements.extra["robinhoodChainId"] == ROBINHOOD_CHAIN_ID
    assert decision.order_draft is not None
    assert decision.order_draft["execution_enabled"] is False
    assert decision.order_draft["primary_draft"]["venue"] == "robinhood_chain_testnet_stock_token"
    assert decision.order_draft["primary_draft"]["payload"]["stock_token"] == "PLTR"


def test_blocked_attempt_flags_prompt_injection_and_domain():
    decision = evaluate_attempt(blocked_attempt(), default_mandate())

    assert decision.approved is False
    assert set(decision.risk_flags) >= {"domain_not_allowed", "prompt_injection"}
    assert decision.chain_anchor["approved"] is False


def test_spend_limit_exceeded_blocks_payment():
    payload = {
        "resource": default_attempt().resource,
        "amount_usdc": "99.0",
        "action": "buy-private-signal",
        "payload_summary": "normal paid lookup",
        "result_summary": "normal result",
    }

    decision = evaluate_from_payload(payload)

    assert decision["approved"] is False
    assert "spend_limit_exceeded" in decision["risk_flags"]


def test_demo_state_contains_privacy_and_safety_claims():
    state = build_demo_state()

    assert state["project"]["mode"] == "testnet_paper_only"
    assert state["approved_flow"]["approved"] is True
    assert state["blocked_flow"]["approved"] is False
    assert state["safety"]["live_trading_enabled"] is False
    assert state["safety"]["telegram_sends_enabled"] is False
    assert state["mandate"]["remaining_usdc"] == str(Decimal("1.63").normalize())
