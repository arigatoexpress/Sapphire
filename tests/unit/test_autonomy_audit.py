"""Tests for structured autonomy audit logging."""

from __future__ import annotations

import json
from pathlib import Path

from lib.core.autonomy_audit import AutonomyAuditLog, sanitize_metadata


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_append_writes_structured_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "autonomy.jsonl"
    audit = AutonomyAuditLog(path, now=lambda: 123.0)

    audit.append(
        "autonomy.decision_evaluated",
        actor="decision_engine",
        action="evaluate_signal",
        outcome="allow",
        risk="financial_decision",
        object_ref="sig-1",
        metadata={"symbol": "BTC", "rules_fired": ["regime_penalty"]},
    )

    record = _records(path)[0]
    assert record["event_type"] == "autonomy.decision_evaluated"
    assert record["ts"] == 123.0
    assert record["actor"] == "decision_engine"
    assert "object_ref" not in record
    assert record["object_ref_hash"]
    assert record["object_ref_chars"] == len("sig-1")
    assert record["metadata"]["symbol"] == "BTC"


def test_disabled_audit_path_writes_nothing(tmp_path: Path) -> None:
    audit = AutonomyAuditLog(False)

    audit.append(
        "autonomy.decision_evaluated",
        actor="decision_engine",
        action="evaluate_signal",
        outcome="allow",
    )

    assert list(tmp_path.rglob("*.jsonl")) == []


def test_metadata_redacts_secret_keys_and_bearer_text() -> None:
    metadata = sanitize_metadata(
        {
            "api_key": "abc123",
            "nested": {"Authorization": "Bearer secret-token-value"},
            "note": "token=raw-secret should vanish",
        }
    )

    serialized = json.dumps(metadata)
    assert "abc123" not in serialized
    assert "secret-token-value" not in serialized
    assert "raw-secret" not in serialized
    assert metadata["api_key"] == "<redacted>"
