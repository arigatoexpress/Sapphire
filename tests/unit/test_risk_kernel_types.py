from __future__ import annotations

from lib.core import risk_kernel
from lib.core.risk_kernel import DecisionEnvelope, PolicyResult, RiskVerdict


def test_decision_envelope_from_mapping_coerces_public_aliases() -> None:
    envelope = DecisionEnvelope.from_mapping(
        {
            "id": "alias-id",
            "order_type": "limit",
            "direction": "long",
            "symbol": "BTC-USD",
            "quantity": "0.25",
            "price": "65000.5",
            "position_usd": "16250.125",
            "position_pct": "0.1625",
            "equity_estimate": "100000",
            "confidence": "0.77",
            "stop_loss": "62000",
            "reduce_only": "enabled",
            "risk_metrics": {"atr": "1500.25", "daily_loss_pct": "1.5"},
            "market_data": {"spread_bps": "4.2"},
            "metadata": {"operator": "codex"},
            "created_at": "2026-04-28T04:00:00+00:00",
        }
    )

    assert envelope.decision_id == "alias-id"
    assert envelope.action == "limit"
    assert envelope.side == "long"
    assert envelope.quantity == 0.25
    assert envelope.price == 65000.5
    assert envelope.notional_usd == 16250.125
    assert envelope.proposed_position_pct == 0.1625
    assert envelope.equity == 100000.0
    assert envelope.atr == 1500.25
    assert envelope.stop_loss_price == 62000.0
    assert envelope.confidence == 0.77
    assert envelope.reduce_only is True
    assert envelope.risk_metrics["daily_loss_pct"] == "1.5"
    assert envelope.market_data["spread_bps"] == "4.2"
    assert envelope.metadata["operator"] == "codex"


def test_decision_envelope_from_mapping_generates_stable_id() -> None:
    payload = {
        "action": "open_order",
        "symbol": "ETH-USD",
        "risk_metrics": {"daily_loss_pct": 0.5},
    }

    first = DecisionEnvelope.from_mapping(payload)
    second = DecisionEnvelope.from_mapping(dict(reversed(list(payload.items()))))

    assert first.decision_id.startswith("decision-")
    assert first.decision_id == second.decision_id


def test_decision_envelope_metric_uses_public_precedence_order() -> None:
    envelope = DecisionEnvelope(
        decision_id="metric-precedence",
        action="open_order",
        price=101.0,
        risk_metrics={"price": 202.0, "drawdown_pct": 1.2},
        market_data={"spread_bps": 3.4, "drawdown_pct": 9.9},
        metadata={"venue": "paper", "spread_bps": 8.8},
    )

    assert envelope.metric("price") == 101.0
    assert envelope.metric("drawdown_pct") == 1.2
    assert envelope.metric("spread_bps") == 3.4
    assert envelope.metric("venue") == "paper"
    assert envelope.metric("missing", "fallback") == "fallback"


def test_policy_result_to_dict_includes_fired_state() -> None:
    blocked = PolicyResult(
        policy="daily_loss",
        version="0.1.0",
        passed=False,
        reason="loss exceeded",
    )
    passed = PolicyResult(
        policy="daily_loss",
        version="0.1.0",
        passed=True,
        reason="within limit",
    )

    assert blocked.fired is True
    assert blocked.to_dict()["fired"] is True
    assert passed.fired is False
    assert passed.to_dict()["fired"] is False


def test_risk_verdict_to_dict_serializes_full_tree() -> None:
    ok = PolicyResult("ok_policy", "0.1.0", True, "clear")
    blocked = PolicyResult(
        "blocked_policy",
        "0.1.0",
        False,
        "blocked",
        metrics={"risk": 2},
        params={"limit": 1},
    )
    verdict = RiskVerdict(
        decision_id="verdict-1",
        allowed=False,
        policy_results=(ok, blocked),
        generated_at="2026-04-28T04:00:00+00:00",
        evaluation_ms=1.25,
    )

    payload = verdict.to_dict()

    assert verdict.fired_gates == (blocked,)
    assert payload["schema_version"] == 1
    assert payload["kernel_version"] == "0.1.0"
    assert payload["decision_id"] == "verdict-1"
    assert payload["allowed"] is False
    assert [item["policy"] for item in payload["policy_results"]] == [
        "ok_policy",
        "blocked_policy",
    ]
    assert [item["policy"] for item in payload["fired_gates"]] == ["blocked_policy"]
    assert payload["fired_gates"][0]["metrics"] == {"risk": 2}
    assert payload["fired_gates"][0]["params"] == {"limit": 1}


def test_risk_kernel_package_reexports_versioned_public_types() -> None:
    expected = {
        "DecisionEnvelope",
        "PolicyResult",
        "RiskPolicy",
        "RiskVerdict",
        "RiskKernelV1",
        "default_policies",
        "__version__",
    }

    assert expected.issubset(set(risk_kernel.__all__))
    for name in expected:
        assert hasattr(risk_kernel, name)
    assert risk_kernel.__version__ == "0.1.0"
