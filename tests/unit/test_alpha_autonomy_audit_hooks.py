"""Tests for Alpha autonomy audit hooks."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALPHA_ROOT = ROOT / "services" / "alpha"
if str(ALPHA_ROOT) not in sys.path:
    sys.path.insert(0, str(ALPHA_ROOT))

from src.autonomy_audit_hooks import append_alpha_session_decision_audit  # noqa: E402


def test_session_decision_audit_hashes_sensitive_identifiers(monkeypatch, tmp_path):
    audit_path = tmp_path / "autonomy.jsonl"
    monkeypatch.setenv("SAPPHIRE_AUTONOMY_AUDIT_LOG", str(audit_path))

    append_alpha_session_decision_audit(
        session_key="hook:autonomy:123 token=sample-token",
        decision="APPROVE",
        source="telegram:123 password=sample-password",
        dispatched=True,
        reason="accepted via gateway secret=sample-secret",
        hook_result={
            "dispatched": True,
            "session_key": "remote-key-should-not-render",
            "payload": {"raw": "payload-should-not-render"},
        },
        note_chars=42,
    )

    record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    serialized = json.dumps(record)
    metadata = record["metadata"]

    assert record["event_type"] == "autonomy.session_decision_applied"
    assert record["actor"] == "alpha_engine"
    assert record["action"] == "apply_session_decision"
    assert record["outcome"] == "approved_dispatched"
    assert record["object_ref"] == "alpha_autonomy_session"
    assert metadata["decision"] == "approve"
    assert metadata["dispatched"] is True
    assert metadata["reason_code"] == "accepted_via_gateway_secret_redacted"
    assert metadata["session_key_hash"]
    assert metadata["source_hash"]
    assert metadata["note_chars"] == 42
    assert metadata["hook_result_keys"] == ["dispatched", "payload", "session_key"]
    assert "sample-token" not in serialized
    assert "sample-password" not in serialized
    assert "sample-secret" not in serialized
    assert "remote-key-should-not-render" not in serialized
    assert "payload-should-not-render" not in serialized
    assert "hook:autonomy:123" not in serialized
    assert "telegram:123" not in serialized


def test_session_decision_audit_records_rejection_not_dispatched(monkeypatch, tmp_path):
    audit_path = tmp_path / "autonomy.jsonl"
    monkeypatch.setenv("SAPPHIRE_AUTONOMY_AUDIT_LOG", str(audit_path))

    append_alpha_session_decision_audit(
        session_key="session-1",
        decision="REJECT",
        source="owner",
        dispatched=False,
        reason="no_dispatcher_available",
    )

    record = json.loads(audit_path.read_text(encoding="utf-8").strip())

    assert record["outcome"] == "rejected_not_dispatched"
    assert record["metadata"]["reason_code"] == "no_dispatcher_available"
    assert record["metadata"]["hook_result_keys"] == []


def test_alpha_engine_session_decision_path_calls_audit_hook() -> None:
    tree = ast.parse((ALPHA_ROOT / "src" / "main.py").read_text(encoding="utf-8"))
    target_method: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_apply_autonomy_session_decision":
            target_method = node
            break

    assert target_method is not None
    calls = [
        node
        for node in ast.walk(target_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "append_alpha_session_decision_audit"
    ]
    assert len(calls) == 1
    keyword_names = {kw.arg for kw in calls[0].keywords}
    assert {
        "session_key",
        "decision",
        "source",
        "dispatched",
        "reason",
        "hook_result",
        "note_chars",
    } <= keyword_names
