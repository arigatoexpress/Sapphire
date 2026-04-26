"""Tests for services/dashboard/strategy_ops/runtime.py.

Covers the three pure builders that produce the dashboard's
strategy-operations go/no-go payload from a raw scorecard, an operator
brief, a data-quality block, and a reject-tax summary.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "services" / "dashboard" / "strategy_ops" / "runtime.py"

_spec = importlib.util.spec_from_file_location("strategy_ops_runtime", SRC)
runtime = importlib.util.module_from_spec(_spec)
sys.modules["strategy_ops_runtime"] = runtime
_spec.loader.exec_module(runtime)


# --- _as_float -------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, 1.0),
        ("2.5", 2.5),
        (None, 0.0),
        ("not-a-number", 0.0),
        ([], 0.0),
        ({}, 0.0),
    ],
)
def test_as_float_returns_default_on_uncoerceable(value, expected):
    assert runtime._as_float(value, default=0.0) == expected


def test_as_float_uses_explicit_default():
    assert runtime._as_float(None, default=99.0) == 99.0


# --- build_strategy_ops_assessment ----------------------------------------


def test_assessment_go_when_thresholds_met(monkeypatch):
    monkeypatch.delenv("STRATEGY_OPS_GONOGO_MIN_SAMPLE_SIZE", raising=False)
    monkeypatch.delenv("STRATEGY_OPS_GONOGO_MAX_REJECT_TAX_PCT", raising=False)
    monkeypatch.delenv("STRATEGY_OPS_GONOGO_MAX_HARD_FAIL_PCT", raising=False)
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {"sample_size": 100}, "ranked": []},
        reject_tax={"sample_size": 100, "reject_tax_pct": 30.0, "hard_fail_pct": 5.0},
    )
    assert out["go"] is True
    assert out["label"] == "GO"
    assert out["reasons"] == []


def test_assessment_no_go_below_min_sample_size(monkeypatch):
    monkeypatch.delenv("STRATEGY_OPS_GONOGO_MIN_SAMPLE_SIZE", raising=False)
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {}, "ranked": []},
        reject_tax={"sample_size": 5, "reject_tax_pct": 10.0, "hard_fail_pct": 1.0},
    )
    assert out["go"] is False
    assert out["label"] == "NO-GO"
    assert any("sample_size" in r for r in out["reasons"])


def test_assessment_no_go_above_max_reject_tax():
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {}, "ranked": []},
        reject_tax={"sample_size": 100, "reject_tax_pct": 90.0, "hard_fail_pct": 1.0},
    )
    assert out["go"] is False
    assert any("reject_tax" in r for r in out["reasons"])


def test_assessment_no_go_above_max_hard_fail():
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {}, "ranked": []},
        reject_tax={"sample_size": 100, "reject_tax_pct": 30.0, "hard_fail_pct": 50.0},
    )
    assert out["go"] is False
    assert any("hard_fail" in r for r in out["reasons"])


def test_assessment_includes_promote_candidates_count():
    ranked = [
        {"strategy": "rsi", "timeframe": "1h", "recommendation": "promote"},
        {"strategy": "macd", "timeframe": "4h", "recommendation": "drop"},
        {"strategy": "bb", "timeframe": "1d", "recommendation": "PROMOTE"},
    ]
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {}, "ranked": ranked},
        reject_tax={"sample_size": 100, "reject_tax_pct": 30.0, "hard_fail_pct": 5.0},
    )
    assert out["promote_candidates"] == 2


def test_assessment_returns_top_promote_lane_label():
    ranked = [
        {"strategy": "rsi-mean-revert", "timeframe": "1h", "recommendation": "promote"},
    ]
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {}, "ranked": ranked},
        reject_tax={"sample_size": 100, "reject_tax_pct": 30.0, "hard_fail_pct": 5.0},
    )
    assert out["top_promote_lane"] == "rsi-mean-revert@1h"


def test_assessment_empty_top_promote_lane_when_none():
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {}, "ranked": []},
        reject_tax={"sample_size": 100, "reject_tax_pct": 30.0, "hard_fail_pct": 5.0},
    )
    assert out["top_promote_lane"] == ""


def test_assessment_falls_back_to_scorecard_totals_for_sample_size():
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {"sample_size": 100, "reject_tax_pct": 30.0}, "ranked": []},
        reject_tax={},
    )
    assert out["sample_size"] == 100


def test_assessment_env_overrides_thresholds(monkeypatch):
    monkeypatch.setenv("STRATEGY_OPS_GONOGO_MIN_SAMPLE_SIZE", "10")
    monkeypatch.setenv("STRATEGY_OPS_GONOGO_MAX_REJECT_TAX_PCT", "50")
    monkeypatch.setenv("STRATEGY_OPS_GONOGO_MAX_HARD_FAIL_PCT", "5")
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": {}, "ranked": []},
        reject_tax={"sample_size": 12, "reject_tax_pct": 40.0, "hard_fail_pct": 4.0},
    )
    assert out["go"] is True
    assert out["thresholds"]["min_sample_size"] == 10
    assert out["thresholds"]["max_reject_tax_pct"] == 50.0
    assert out["thresholds"]["max_hard_fail_pct"] == 5.0


def test_assessment_handles_non_dict_scorecard_safely():
    out = runtime.build_strategy_ops_assessment(
        scorecard={"totals": "not a dict", "ranked": "not a list"},
        reject_tax={"sample_size": 100, "reject_tax_pct": 30.0, "hard_fail_pct": 5.0},
    )
    assert out["go"] is True  # totals/ranked guards default empty
    assert out["promote_candidates"] == 0


# --- resolve_strategy_ops_decision ----------------------------------------


def test_resolve_decision_returns_go_when_assessment_and_operator_agree():
    out = runtime.resolve_strategy_ops_decision(
        assessment={"go": True, "label": "GO", "reasons": []},
        operator_brief={"go": True, "label": "GO", "hard_blockers": []},
        data_quality={"degraded": False},
    )
    assert out["go"] is True
    assert out["label"] == "GO"
    assert out["diverged"] is False


def test_resolve_decision_no_go_when_operator_overrides():
    out = runtime.resolve_strategy_ops_decision(
        assessment={"go": True, "label": "GO", "reasons": []},
        operator_brief={"go": False, "label": "NO-GO", "hard_blockers": ["risk too high"]},
        data_quality={"degraded": False},
    )
    assert out["go"] is False
    assert out["diverged"] is True
    assert "risk too high" in out["reasons"]


def test_resolve_decision_data_quality_degraded_forces_no_go():
    out = runtime.resolve_strategy_ops_decision(
        assessment={"go": True, "label": "GO", "reasons": []},
        operator_brief={"go": True, "label": "GO", "hard_blockers": []},
        data_quality={"degraded": True, "degraded_sources": ["coingecko", "openbb"]},
    )
    assert out["go"] is False
    assert out["label"] == "NO-GO"
    assert out["data_quality_degraded"] is True
    assert any("data_quality" in r.lower() for r in out["reasons"])


def test_resolve_decision_caps_reasons_at_eight():
    out = runtime.resolve_strategy_ops_decision(
        assessment={"go": False, "label": "NO-GO", "reasons": [f"r{i}" for i in range(20)]},
        operator_brief={"go": False, "label": "NO-GO", "hard_blockers": []},
        data_quality={"degraded": False},
    )
    assert len(out["reasons"]) == 8


def test_resolve_decision_caps_degraded_sources_at_five():
    out = runtime.resolve_strategy_ops_decision(
        assessment={"go": True, "label": "GO", "reasons": []},
        operator_brief={"go": True, "label": "GO", "hard_blockers": []},
        data_quality={"degraded": True, "degraded_sources": [f"src{i}" for i in range(20)]},
    )
    assert len(out["degraded_sources"]) == 5


def test_resolve_decision_handles_none_inputs_gracefully():
    out = runtime.resolve_strategy_ops_decision(
        assessment=None,
        operator_brief=None,
        data_quality=None,
    )
    assert out["go"] is False
    assert out["label"] == "NO-GO"


def test_resolve_decision_strips_whitespace_only_reasons():
    """Empty / whitespace-only reasons are stripped. None coerces to "None"
    string and survives — see PR #226 behaviour notes for the bug."""
    out = runtime.resolve_strategy_ops_decision(
        assessment={"go": False, "reasons": ["", "   ", "real reason"]},
        operator_brief={"go": False, "hard_blockers": []},
        data_quality={"degraded": False},
    )
    assert out["reasons"] == ["real reason"]


# --- build_go_no_go_brief_payload -----------------------------------------


def test_brief_payload_carries_decision_summary():
    payload = runtime.build_go_no_go_brief_payload(
        ops_payload={
            "decision": {"label": "GO", "go": True, "source": "operator_brief"},
            "operator_brief": {"why_this_matters_now": "BTC at all-time high"},
            "reject_tax": {"sample_size": 100, "reject_tax_pct": 30.0, "hard_fail_pct": 5.0},
            "attribution": {"net_pnl_after_fees": 1234.5, "max_drawdown_pct": 7.0},
        },
        window_days=30,
        timestamp="2026-04-26T21:00:00Z",
    )
    assert payload["timestamp"] == "2026-04-26T21:00:00Z"
    assert payload["window_days"] == 30
    assert payload["summary"]["decision_label"] == "GO"
    assert payload["summary"]["decision_go"] is True
    assert payload["summary"]["sample_size"] == 100
    assert payload["why_this_matters_now"] == "BTC at all-time high"


def test_brief_payload_caps_top_actions_at_three():
    payload = runtime.build_go_no_go_brief_payload(
        ops_payload={
            "operator_brief": {"top_actions": [f"action{i}" for i in range(10)]},
        },
        window_days=7,
        timestamp="2026-04-26T21:00:00Z",
    )
    assert len(payload["top_actions"]) == 3


def test_brief_payload_caps_top_lanes_at_three():
    payload = runtime.build_go_no_go_brief_payload(
        ops_payload={
            "scorecard": {"ranked": [f"lane{i}" for i in range(10)]},
        },
        window_days=7,
        timestamp="2026-04-26T21:00:00Z",
    )
    assert len(payload["top_lanes"]) == 3


def test_brief_payload_falls_back_to_operator_blockers_when_decision_has_none():
    payload = runtime.build_go_no_go_brief_payload(
        ops_payload={
            "decision": {"reasons": []},
            "operator_brief": {"hard_blockers": ["risk", "data quality"]},
        },
        window_days=7,
        timestamp="2026-04-26T21:00:00Z",
    )
    assert payload["hard_blockers"] == ["risk", "data quality"]


def test_brief_payload_handles_missing_blocks():
    payload = runtime.build_go_no_go_brief_payload(
        ops_payload={},
        window_days=14,
        timestamp="2026-04-26T21:00:00Z",
    )
    assert payload["timestamp"] == "2026-04-26T21:00:00Z"
    assert payload["window_days"] == 14
    assert payload["summary"]["decision_label"] == "NO-GO"
    assert payload["hard_blockers"] == []
    assert payload["top_actions"] == []
    assert payload["top_lanes"] == []


def test_brief_payload_includes_static_sources_block():
    payload = runtime.build_go_no_go_brief_payload(
        ops_payload={},
        window_days=7,
        timestamp="2026-04-26T21:00:00Z",
    )
    assert payload["sources"] == {
        "strategy_ops": "/api/platform/strategy-ops",
        "agent_context": "/api/platform/agent-context",
    }
