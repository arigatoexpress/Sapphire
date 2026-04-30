"""Unit tests for the Pine + alerts surface on the TradingView orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lib.trading.tradingview_orchestrator import TradingViewOrchestrator


@pytest.fixture
def orch(tmp_path: Path) -> TradingViewOrchestrator:
    return TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_path,
        mutation_enabled=False,
    )


@pytest.fixture
def orch_mutating(tmp_path: Path) -> TradingViewOrchestrator:
    return TradingViewOrchestrator(
        tv_bin="echo",
        artifact_root=tmp_path,
        mutation_enabled=True,
    )


# Pine read-only ------------------------------------------------------------------


def test_pine_list_calls_tv_pine_list(orch: TradingViewOrchestrator):
    with patch.object(orch, "_run", return_value={"ok": True, "payload": {"scripts": []}}) as run:
        orch.pine_list()
        run.assert_called_once_with("pine", "list")


def test_pine_get_calls_tv_pine_get(orch: TradingViewOrchestrator):
    with patch.object(orch, "_run", return_value={"ok": True}) as run:
        orch.pine_get()
        run.assert_called_once_with("pine", "get")


def test_pine_check_file_passes_path(orch: TradingViewOrchestrator):
    with patch.object(orch, "_run", return_value={"ok": True}) as run:
        orch.pine_check_file("/tmp/foo.pine")
        run.assert_called_once_with("pine", "check", "-f", "/tmp/foo.pine")


def test_pine_validate_combines_analyze_and_check(orch: TradingViewOrchestrator):
    def fake(*args, **kwargs):
        if args[1] == "analyze":
            return {"ok": True, "payload": {"diagnostics": []}}
        return {"ok": True, "payload": {"compiled": True}}

    with patch.object(orch, "_run", side_effect=fake):
        result = orch.pine_validate_file("/tmp/foo.pine")
    assert result["ok"] is True
    assert result["analyze"]["ok"] is True
    assert result["check"]["ok"] is True


def test_pine_validate_fails_when_either_step_fails(orch: TradingViewOrchestrator):
    def fake(*args, **kwargs):
        if args[1] == "analyze":
            return {"ok": False, "stderr": "broken"}
        return {"ok": True}

    with patch.object(orch, "_run", side_effect=fake):
        result = orch.pine_validate_file("/tmp/foo.pine")
    assert result["ok"] is False


# Pine mutations ------------------------------------------------------------------


def test_pine_open_blocked_without_gate(orch: TradingViewOrchestrator):
    res = orch.pine_open("Sapphire Watch")
    assert res["mutated"] is False
    assert "SAPPHIRE_TV_MUTATION_ENABLED" in res["reason"]


def test_pine_open_runs_when_gated(orch_mutating: TradingViewOrchestrator):
    with patch.object(orch_mutating, "_run", return_value={"ok": True}) as run:
        orch_mutating.pine_open("Sapphire Watch")
        run.assert_called_once_with("pine", "open", "Sapphire Watch")


def test_pine_set_from_file_blocked_without_gate(orch: TradingViewOrchestrator):
    assert orch.pine_set_from_file("/tmp/x.pine")["mutated"] is False


def test_pine_set_from_file_runs_when_gated(orch_mutating: TradingViewOrchestrator):
    with patch.object(orch_mutating, "_run", return_value={"ok": True}) as run:
        orch_mutating.pine_set_from_file("/tmp/x.pine")
        run.assert_called_once_with("pine", "set", "--file", "/tmp/x.pine")


def test_pine_compile_blocked_without_gate(orch: TradingViewOrchestrator):
    assert orch.pine_compile()["mutated"] is False


def test_pine_save_blocked_without_gate(orch: TradingViewOrchestrator):
    assert orch.pine_save()["mutated"] is False


# Pine promote --------------------------------------------------------------------


def test_pine_promote_blocked_without_gate(orch: TradingViewOrchestrator):
    res = orch.pine_promote("/tmp/foo.pine")
    assert res["mutated"] is False
    assert "SAPPHIRE_TV_MUTATION_ENABLED" in res["reason"]


def test_pine_promote_stops_at_first_failed_stage(orch_mutating: TradingViewOrchestrator):
    def fake(*args, **kwargs):
        # pine set fails — should never reach compile/errors/save
        if args[:2] == ("pine", "set"):
            return {
                "ok": False,
                "returncode": 1,
                "stderr": "no editor",
                "command": "tv pine set --file /tmp/foo.pine",
                "stdout": "",
                "payload": None,
                "parse_error": None,
            }
        raise AssertionError(f"unexpected _run call after failure: {args}")

    with patch.object(orch_mutating, "_run", side_effect=fake) as run:
        result = orch_mutating.pine_promote("/tmp/foo.pine")

    assert result["ok"] is False
    assert result["mutated"] is True
    assert result["stage"] == "set"
    assert "set" in result["stages"]
    assert "compile" not in result["stages"]
    assert "errors" not in result["stages"]
    assert "save" not in result["stages"]
    # Only the pine_set call should have run
    assert run.call_count == 1


def test_pine_promote_happy_path_runs_all_four_stages(
    orch_mutating: TradingViewOrchestrator,
):
    calls: list[tuple] = []

    def fake(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("pine", "set"):
            return {"ok": True, "stdout": "set", "stderr": "", "payload": None}
        if args[:2] == ("pine", "compile"):
            return {"ok": True, "stdout": "compiled", "stderr": "", "payload": {"compiled": True}}
        if args[:2] == ("pine", "errors"):
            return {"ok": True, "stdout": "", "stderr": "", "payload": {"errors": []}}
        if args[:2] == ("pine", "save"):
            return {"ok": True, "stdout": "saved", "stderr": "", "payload": {"saved": True}}
        raise AssertionError(f"unexpected _run call: {args}")

    with patch.object(orch_mutating, "_run", side_effect=fake):
        result = orch_mutating.pine_promote("/tmp/foo.pine")

    assert result["ok"] is True
    assert result["mutated"] is True
    assert result["path"] == "/tmp/foo.pine"
    assert set(result["stages"].keys()) == {"set", "compile", "errors", "save"}
    # Each stage's raw result is preserved
    assert result["stages"]["set"]["ok"] is True
    assert result["stages"]["compile"]["payload"] == {"compiled": True}
    assert result["stages"]["errors"]["payload"] == {"errors": []}
    assert result["stages"]["save"]["payload"] == {"saved": True}
    # All four tv calls happened in order
    assert [c[:2] for c in calls] == [
        ("pine", "set"),
        ("pine", "compile"),
        ("pine", "errors"),
        ("pine", "save"),
    ]


def test_pine_promote_fails_when_compile_reports_errors(
    orch_mutating: TradingViewOrchestrator,
):
    def fake(*args, **kwargs):
        if args[:2] == ("pine", "set"):
            return {"ok": True, "payload": None}
        if args[:2] == ("pine", "compile"):
            return {"ok": True, "payload": {"compiled": True}}
        if args[:2] == ("pine", "errors"):
            return {
                "ok": True,
                "payload": {
                    "errors": [{"line": 12, "message": "Undeclared identifier 'foo'"}]
                },
            }
        raise AssertionError(f"unexpected _run call after errors: {args}")

    with patch.object(orch_mutating, "_run", side_effect=fake):
        result = orch_mutating.pine_promote("/tmp/foo.pine")

    assert result["ok"] is False
    assert result["stage"] == "errors"
    assert result["errors"] == [{"line": 12, "message": "Undeclared identifier 'foo'"}]
    # save should NOT have run
    assert "save" not in result["stages"]


# Alerts --------------------------------------------------------------------------


def test_alerts_list_calls_tv_alert_list(orch: TradingViewOrchestrator):
    with patch.object(orch, "_run", return_value={"ok": True, "payload": {"alert_count": 7}}) as run:
        orch.alerts_list()
        run.assert_called_once_with("alert", "list")


def test_alert_create_blocked_without_gate(orch: TradingViewOrchestrator):
    res = orch.alert_create(price=42000.0, condition="greater_than", message="hi")
    assert res["mutated"] is False


def test_alert_create_validates_condition(orch_mutating: TradingViewOrchestrator):
    res = orch_mutating.alert_create(price=42000.0, condition="bogus")
    assert res["ok"] is False
    assert "invalid condition" in res["reason"]


def test_alert_create_passes_args_when_gated(orch_mutating: TradingViewOrchestrator):
    with patch.object(orch_mutating, "_run", return_value={"ok": True}) as run:
        orch_mutating.alert_create(price=100.5, condition="crossing", message="x")
        run.assert_called_once_with(
            "alert", "create", "-p", "100.5", "-c", "crossing", "-m", "x"
        )


def test_alert_delete_blocked_without_gate(orch: TradingViewOrchestrator):
    assert orch.alert_delete()["mutated"] is False


def test_alert_delete_passes_id_when_gated(orch_mutating: TradingViewOrchestrator):
    with patch.object(orch_mutating, "_run", return_value={"ok": True}) as run:
        orch_mutating.alert_delete(alert_id=12345)
        run.assert_called_once_with("alert", "delete", "12345")
