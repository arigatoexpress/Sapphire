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

from src.autonomy_audit_hooks import (  # noqa: E402
    append_alpha_dispatch_evaluation_audit,
    append_alpha_session_created_audit,
    append_alpha_session_decision_audit,
)


def test_session_created_audit_hashes_session_and_omits_instruction(monkeypatch, tmp_path):
    audit_path = tmp_path / "autonomy.jsonl"
    monkeypatch.setenv("SAPPHIRE_AUTONOMY_AUDIT_LOG", str(audit_path))

    append_alpha_session_created_audit(
        session_key="hook:created:123 token=sample-token",
        trigger="manual telegram password=sample-password",
        instruction_chars=len("do not render this generated instruction"),
        approval_required=True,
    )

    record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    serialized = json.dumps(record)
    metadata = record["metadata"]

    assert record["event_type"] == "autonomy.session_created"
    assert record["actor"] == "alpha_engine"
    assert record["action"] == "record_autonomy_session"
    assert record["outcome"] == "pending"
    assert "object_ref" not in record
    assert record["object_ref_hash"]
    assert record["object_ref_chars"] == len("alpha_autonomy_session")
    assert metadata["session_key_hash"]
    assert metadata["trigger_code"] == "manual_telegram_password_redacted"
    assert metadata["instruction_chars"] > 0
    assert metadata["approval_required"] is True
    assert "sample-token" not in serialized
    assert "sample-password" not in serialized
    assert "hook:created:123" not in serialized
    assert "do not render this generated instruction" not in serialized


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
    assert "object_ref" not in record
    assert record["object_ref_hash"]
    assert record["object_ref_chars"] == len("alpha_autonomy_session")
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


def test_dispatch_evaluation_audit_summarizes_context(monkeypatch, tmp_path):
    audit_path = tmp_path / "autonomy.jsonl"
    monkeypatch.setenv("SAPPHIRE_AUTONOMY_AUDIT_LOG", str(audit_path))

    append_alpha_dispatch_evaluation_audit(
        trigger="manual token=sample-token",
        agent_id="OBSIDIAN password=sample-password",
        outcome="dry_run",
        reason="hook secret=sample-secret",
        context={
            "active_venues": ["ASTER", "LIGHTER"],
            "preferred_symbols": ["BTC", "ETH", "SOL"],
            "venue_profiles": {"ASTER": {"role": "momentum"}},
            "pending_autonomy_sessions": "2",
            "total_failure_pressure": "3.25",
            "raw_instruction": "do not serialize this instruction",
        },
        allow_code_changes=True,
        allow_gcloud_changes=False,
        approval_required=True,
    )

    record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    serialized = json.dumps(record)
    metadata = record["metadata"]

    assert record["event_type"] == "autonomy.dispatch_evaluated"
    assert record["actor"] == "alpha_engine"
    assert record["action"] == "evaluate_full_autonomy_dispatch"
    assert record["outcome"] == "dry_run"
    assert "object_ref" not in record
    assert record["object_ref_hash"]
    assert record["object_ref_chars"] == len("alpha_full_autonomy")
    assert metadata["trigger_code"] == "manual_token_redacted"
    assert metadata["agent_code"] == "obsidian_password_redacted"
    assert metadata["reason_code"] == "hook_secret_redacted"
    assert metadata["active_venue_count"] == 2
    assert metadata["preferred_symbol_count"] == 3
    assert metadata["venue_profile_count"] == 1
    assert metadata["pending_session_count"] == 2
    assert metadata["failure_pressure"] == 3.25
    assert metadata["allow_code_changes"] is True
    assert metadata["allow_gcloud_changes"] is False
    assert metadata["approval_required"] is True
    assert "sample-token" not in serialized
    assert "sample-password" not in serialized
    assert "sample-secret" not in serialized
    assert "do not serialize this instruction" not in serialized
    assert "ASTER" not in serialized
    assert "BTC" not in serialized


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


def test_alpha_engine_session_created_path_calls_audit_hook() -> None:
    tree = ast.parse((ALPHA_ROOT / "src" / "main.py").read_text(encoding="utf-8"))
    target_method: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_record_autonomy_session":
            target_method = node
            break

    assert target_method is not None
    calls = [
        node
        for node in ast.walk(target_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "append_alpha_session_created_audit"
    ]
    assert len(calls) == 1
    keyword_names = {kw.arg for kw in calls[0].keywords}
    assert {
        "session_key",
        "trigger",
        "instruction_chars",
        "approval_required",
    } <= keyword_names


def test_alpha_engine_dispatch_evaluation_path_calls_audit_hook() -> None:
    tree = ast.parse((ALPHA_ROOT / "src" / "main.py").read_text(encoding="utf-8"))
    target_method: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_dispatch_full_autonomy_cycle":
            target_method = node
            break

    assert target_method is not None
    calls = [
        node
        for node in ast.walk(target_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "append_alpha_dispatch_evaluation_audit"
    ]
    outcomes = {
        kw.value.value
        for call in calls
        for kw in call.keywords
        if kw.arg == "outcome" and isinstance(kw.value, ast.Constant)
    }
    assert outcomes == {
        "full_autonomy_disabled",
        "rate_limited",
        "dry_run",
        "no_dispatcher_available",
        "not_dispatched",
    }
    for call in calls:
        keyword_names = {kw.arg for kw in call.keywords}
        assert {
            "trigger",
            "agent_id",
            "outcome",
            "allow_code_changes",
            "allow_gcloud_changes",
            "approval_required",
        } <= keyword_names
        outcome = next(
            (
                kw.value.value
                for kw in call.keywords
                if kw.arg == "outcome" and isinstance(kw.value, ast.Constant)
            ),
            "",
        )
        if outcome in {"dry_run", "no_dispatcher_available", "not_dispatched"}:
            assert "context" in keyword_names
