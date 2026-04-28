from __future__ import annotations

from lib.core.risk_kernel import DecisionEnvelope, RiskKernelV1
from lib.core.risk_kernel.policies import DailyLossPolicy


def test_verdict_enumerates_every_fired_gate() -> None:
    verdict = RiskKernelV1().evaluate(
        {
            "decision_id": "multi-fire",
            "action": "open_order",
            "symbol": "BTC-USD",
            "notional_usd": 50000.0,
            "equity": 100000.0,
            "price": 65000.0,
            "atr": 5000.0,
            "risk_metrics": {
                "daily_loss_pct": 4.5,
                "intraday_drawdown_pct": 3.7,
                "kill_switch_active": True,
            },
            "metadata": {"lookahead_bias": True},
        }
    )

    assert verdict.allowed is False
    fired = {result.policy for result in verdict.fired_gates}
    assert fired == {
        "daily_loss",
        "intraday_drawdown",
        "atr_sizing",
        "kill_switch_deference",
        "data_leakage_guard",
    }


def test_custom_policy_set_can_be_one_file_class() -> None:
    kernel = RiskKernelV1(policies=(DailyLossPolicy(max_loss_pct=1.0),))
    verdict = kernel.evaluate(
        DecisionEnvelope(
            decision_id="custom-policy",
            action="open_order",
            risk_metrics={"daily_loss_pct": 1.2},
        )
    )

    assert verdict.allowed is False
    assert [result.policy for result in verdict.fired_gates] == ["daily_loss"]


def test_policy_errors_fail_closed() -> None:
    class BrokenPolicy:
        name = "broken"
        version = "0.0.1"
        params = {"demo": True}

        def check(self, _envelope: DecisionEnvelope):
            raise RuntimeError("boom")

    verdict = RiskKernelV1(policies=(BrokenPolicy(),)).evaluate(
        {"decision_id": "broken-policy", "action": "open_order"}
    )

    assert verdict.allowed is False
    assert verdict.fired_gates[0].policy == "broken"
    assert "policy error" in verdict.fired_gates[0].reason
