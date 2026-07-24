from __future__ import annotations

import json
from pathlib import Path

from lib.core.risk_kernel import DecisionEnvelope, HardRiskKernel, RiskKernelV1

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "redteam"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_risk_kernel_rejects_at_least_95_percent_of_leakage_set() -> None:
    kernel = RiskKernelV1()
    scenarios = _load("risk_kernel_leakage_scenarios.json")
    expected_rejects = [row for row in scenarios if row["expected"] == "reject"]

    rejected = 0
    for row in expected_rejects:
        verdict = kernel.evaluate(row["envelope"])
        if not verdict.allowed:
            rejected += 1

    rejection_rate = rejected / len(expected_rejects)
    assert rejection_rate >= 0.95


def test_risk_kernel_leakage_corpus_has_one_clean_negative() -> None:
    kernel = RiskKernelV1()
    clean = [
        row for row in _load("risk_kernel_leakage_scenarios.json") if row["expected"] == "allow"
    ]
    assert clean
    for row in clean:
        verdict = kernel.evaluate(row["envelope"])
        assert verdict.allowed, verdict.to_dict()


def test_risk_kernel_uses_existing_redteam_sensitive_baselines() -> None:
    kernel = RiskKernelV1()
    probes = _load("sensitivity_classifier_probes.json")
    baseline_sensitive = [
        row for row in probes if row.get("expected") == "sensitive" and not row.get("xfail")
    ]
    assert baseline_sensitive

    for probe in baseline_sensitive:
        envelope = DecisionEnvelope(
            decision_id=f"probe-{probe['id']}",
            action="open_order",
            symbol="BTC-USD",
            notional_usd=1000.0,
            equity=100000.0,
            metadata={"prompt_excerpt": probe["input"], "source_redteam_probe": probe["id"]},
        )
        verdict = kernel.evaluate(envelope)
        assert not verdict.allowed
        assert any(result.policy == "data_leakage_guard" for result in verdict.fired_gates)


def test_public_package_reexports_legacy_hard_risk_kernel() -> None:
    kernel = HardRiskKernel(enabled=True, max_daily_loss_pct=1.0)
    kernel.ingest_equity_snapshot({"equity_estimate": 100.0}, now_ts=1000.0)
    event = kernel.ingest_equity_snapshot({"equity_estimate": 98.0}, now_ts=1001.0)
    assert event is not None
    assert "daily_loss_pct" in event.reason
