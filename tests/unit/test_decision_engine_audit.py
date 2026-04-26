"""Audit-log coverage for the decision engine."""

from __future__ import annotations

import json
from pathlib import Path

from lib.core.decision_engine import DecisionEngine, StateLoader


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_decision_engine_writes_redacted_autonomy_audit(tmp_path: Path) -> None:
    audit_path = tmp_path / "autonomy.jsonl"
    engine = DecisionEngine(
        state_loader=StateLoader(chain_path=tmp_path / "chain.json"),
        decisions_dir=tmp_path / "decisions",
        state_path=tmp_path / "last_regime.json",
        audit_path=audit_path,
    )

    engine.evaluate(
        {
            "signal_id": "sig-1",
            "symbol": "BTC",
            "direction": "long",
            "confidence": 0.70,
            "api_key": "do-not-log",
        },
        world={"regime": "TREND_UP", "token": "do-not-log-world"},
    )

    record = _records(audit_path)[0]
    assert record["event_type"] == "autonomy.decision_evaluated"
    assert record["outcome"] == "allow"
    assert record["risk"] == "financial_decision"
    assert record["metadata"]["symbol"] == "BTC"
    assert record["metadata"]["world_keys"] == ["regime", "token"]
    serialized = json.dumps(record)
    assert "do-not-log" not in serialized
    assert "do-not-log-world" not in serialized


def test_decision_engine_audits_detected_alerts(tmp_path: Path) -> None:
    audit_path = tmp_path / "autonomy.jsonl"
    engine = DecisionEngine(
        state_loader=StateLoader(chain_path=tmp_path / "chain.json"),
        decisions_dir=tmp_path / "decisions",
        state_path=tmp_path / "last_regime.json",
        audit_path=audit_path,
    )

    alerts = engine.scan_alerts({"funding_apr": 0.80, "fear_greed": 12})

    assert {alert.kind for alert in alerts} == {"funding_extreme", "fear_extreme"}
    records = _records(audit_path)
    assert [record["event_type"] for record in records] == [
        "autonomy.alert_detected",
        "autonomy.alert_detected",
    ]
    assert {record["object_ref"] for record in records} == {"funding_extreme", "fear_extreme"}
