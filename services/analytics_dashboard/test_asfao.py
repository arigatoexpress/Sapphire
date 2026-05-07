"""Tests for services/analytics_dashboard/asfao.py — ASFAO decision engine.

Covers:
    * Pure rules catalog — each of the 5 rules tested for fire/no-fire +
      the action shape it emits.
    * register_asfao + endpoint surface — /api/asfao/decide (writes
      proposals to BQ), /api/asfao/decisions (lists), /api/asfao/execute
      (gated by requires_admin).
    * Trading-critical-path action kinds are refused at execute time.

We mock google.cloud.bigquery + auth at import time (mirroring the
existing test_services_analytics_dashboard.py pattern) so no real GCP
or webauthn deps are required.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Path resolution — the asfao module lives in the dashboard service dir,
# alongside auth/ and brain.py. We import it directly via importlib.

SVC_DIR = Path(__file__).resolve().parent
ASFAO_PATH = SVC_DIR / "asfao.py"


def _install_fake_bigquery(monkeypatch):
    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_bigquery.Client = lambda project: types.SimpleNamespace(project=project)

    def _qjc(query_parameters=None):
        return types.SimpleNamespace(query_parameters=query_parameters or [])

    def _sqp(name, kind, value):
        return types.SimpleNamespace(name=name, kind=kind, value=value, _scalar=True)

    def _aqp(name, kind, value):
        return types.SimpleNamespace(name=name, kind=kind, value=value, _array=True)

    fake_bigquery.QueryJobConfig = _qjc
    fake_bigquery.ScalarQueryParameter = _sqp
    fake_bigquery.ArrayQueryParameter = _aqp
    fake_cloud.bigquery = fake_bigquery

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)
    return fake_bigquery


def _load_asfao(monkeypatch):
    """Import asfao.py fresh against the fake bigquery shim."""
    _install_fake_bigquery(monkeypatch)
    monkeypatch.syspath_prepend(str(SVC_DIR))
    sys.modules.pop("asfao", None)
    spec = importlib.util.spec_from_file_location("asfao_test_module", ASFAO_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["asfao_test_module"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def asfao(monkeypatch):
    mod = _load_asfao(monkeypatch)
    yield mod
    sys.modules.pop("asfao_test_module", None)


# ---------------------------------------------------------------------------
# Rules catalog — pure-function tests.
# ---------------------------------------------------------------------------


def test_stale_collector_rule_fires_above_six_hours(asfao):
    syn = {
        "narrative": "Trading: 12 signals/24h.",
        "priority_actions": [
            "regime: collector stale 8.4h — restart com.sapphire.regime-collector",
            "trading: 0 signals — irrelevant for this rule",
        ],
        "degraded_silos": ["regime"],
        "health_score": 0.71,
    }
    fired, decision = asfao.rule_stale_collector_issue(syn, [], {})
    assert fired is True
    assert decision["role"] == "Ops"
    assert decision["action"]["kind"] == "github_issue"
    assert decision["action"]["repo"] == "arigatoexpress/Sapphire"
    assert "regime silent for 8.4h" in decision["action"]["title"]
    assert "auto-filed" in decision["action"]["labels"]
    assert "ops" in decision["action"]["labels"]
    assert decision["trigger"]["silo"] == "regime"
    assert decision["trigger"]["hours_silent"] == 8.4


def test_stale_collector_rule_silent_below_threshold(asfao):
    syn = {
        "priority_actions": [
            "regime: collector stale 4.2h — within threshold",
        ],
    }
    fired, _ = asfao.rule_stale_collector_issue(syn, [], {})
    assert fired is False


def test_stale_collector_rule_silent_when_no_stale_actions(asfao):
    syn = {"priority_actions": ["trading: 0 signals in last 24h"]}
    fired, _ = asfao.rule_stale_collector_issue(syn, [], {})
    assert fired is False


def test_critical_cve_rule_fires_for_stack_match(asfao):
    cves = [
        {
            "cve_id": "CVE-2026-99999",
            "severity": "CRITICAL",
            "cvss_score": 9.8,
            "affected_products": ["Flask 3.1.3 (Pallets)"],
        },
        {
            "cve_id": "CVE-2026-11111",
            "severity": "CRITICAL",
            "affected_products": ["Random Other Vendor X"],
        },
    ]
    fired, decision = asfao.rule_critical_cve_alert({}, [], {"critical_cves_24h": cves})
    assert fired is True
    assert decision["role"] == "Threat"
    assert decision["action"]["kind"] == "telegram_alert"
    assert "CVE-2026-99999" in decision["action"]["text"]
    assert decision["trigger"]["primary_cve"] == "CVE-2026-99999"


def test_critical_cve_rule_silent_when_no_stack_match(asfao):
    cves = [
        {
            "cve_id": "CVE-2026-NOPE",
            "severity": "CRITICAL",
            "affected_products": ["RandomVendorX 1.2"],
        }
    ]
    fired, _ = asfao.rule_critical_cve_alert({}, [], {"critical_cves_24h": cves})
    assert fired is False


def test_critical_cve_rule_silent_when_no_cves(asfao):
    fired, _ = asfao.rule_critical_cve_alert({}, [], {"critical_cves_24h": []})
    assert fired is False


def test_trading_silo_silent_rule_fires_when_live(asfao):
    syn = {"degraded_silos": ["trading", "regime"], "health_score": 0.5}
    ctx = {"hyperliquid_live_enabled": True, "live_executor_label": "hyperliquid"}
    fired, decision = asfao.rule_trading_silo_silent(syn, [], ctx)
    assert fired is True
    assert decision["role"] == "CTO"
    # Crucially: the action is telegram_alert — NOT a trading-critical kind.
    # ASFAO should never auto-pause trading.
    assert decision["action"]["kind"] == "telegram_alert"
    assert decision["action"]["kind"] not in asfao.TRADING_CRITICAL_KINDS
    assert "ASFAO CRITICAL" in decision["action"]["text"]


def test_trading_silo_silent_rule_silent_when_paper_only(asfao):
    syn = {"degraded_silos": ["trading"]}
    ctx = {"hyperliquid_live_enabled": False, "any_live_executor_enabled": False}
    fired, _ = asfao.rule_trading_silo_silent(syn, [], ctx)
    assert fired is False


def test_trading_silo_silent_rule_silent_when_trading_healthy(asfao):
    syn = {"degraded_silos": ["regime"]}
    ctx = {"hyperliquid_live_enabled": True}
    fired, _ = asfao.rule_trading_silo_silent(syn, [], ctx)
    assert fired is False


def test_lead_nurture_rule_fires_with_stale_leads(asfao):
    fired, decision = asfao.rule_lead_nurture({}, [], {"stale_leads_count": 14})
    assert fired is True
    assert decision["role"] == "THO"
    assert decision["action"]["kind"] == "noop"  # operator-driven
    assert "14 LEAD-status leads" in decision["action"]["recommendation"]
    assert decision["trigger"]["stale_leads_count"] == 14


def test_lead_nurture_rule_silent_with_no_stale(asfao):
    fired, _ = asfao.rule_lead_nurture({}, [], {"stale_leads_count": 0})
    assert fired is False


def test_lead_nurture_rule_silent_with_unknown_count(asfao):
    fired, _ = asfao.rule_lead_nurture({}, [], {"stale_leads_count": None})
    assert fired is False


def test_regional_intel_surge_rule_fires_above_2_sigma(asfao):
    surge = {
        "region_id": "north-county",
        "today": 47,
        "mean": 12.0,
        "stddev": 5.0,
        "z": 7.0,
    }
    fired, decision = asfao.rule_regional_intel_surge({}, [], {"regional_surge": surge})
    assert fired is True
    assert decision["role"] == "Strategy"
    assert decision["action"]["kind"] == "telegram_alert"
    assert "north-county" in decision["action"]["text"]
    assert decision["trigger"]["z_score"] == 7.0


def test_regional_intel_surge_rule_silent_below_threshold(asfao):
    surge = {"region_id": "x", "today": 5, "mean": 4.0, "stddev": 2.0, "z": 0.5}
    fired, _ = asfao.rule_regional_intel_surge({}, [], {"regional_surge": surge})
    assert fired is False


def test_regional_intel_surge_rule_silent_when_no_surge(asfao):
    fired, _ = asfao.rule_regional_intel_surge({}, [], {"regional_surge": None})
    assert fired is False


def test_evaluate_rules_collects_multiple_proposals(asfao):
    syn = {
        "priority_actions": [
            "regime: collector stale 12.0h — restart com.sapphire.regime-collector"
        ],
        "degraded_silos": ["regime", "trading"],
    }
    ctx = {
        "critical_cves_24h": [
            {
                "cve_id": "CVE-2026-X",
                "severity": "CRITICAL",
                "affected_products": ["redis 7.x"],
            }
        ],
        "stale_leads_count": 9,
        "regional_surge": None,
        "hyperliquid_live_enabled": False,
    }
    proposals = asfao.evaluate_rules(syn, [], ctx)
    # Should fire: stale_collector + critical_cve + lead_nurture (3)
    assert len(proposals) == 3
    roles = {p["role"] for p in proposals}
    assert {"Ops", "Threat", "THO"}.issubset(roles)


def test_evaluate_rules_swallows_rule_exceptions(asfao, monkeypatch):
    """A buggy rule must not poison the catalog."""

    def _broken(*_a, **_kw):
        raise ValueError("rule blew up")

    monkeypatch.setattr(asfao, "RULES_CATALOG", [_broken, asfao.rule_lead_nurture])
    proposals = asfao.evaluate_rules({}, [], {"stale_leads_count": 5})
    assert len(proposals) == 1  # only lead_nurture fired
    assert proposals[0]["role"] == "THO"


def test_trading_critical_kinds_constant(asfao):
    """Pin the policy: these kinds NEVER auto-execute."""
    assert "trading_pause" in asfao.TRADING_CRITICAL_KINDS
    assert "hyperliquid_order" in asfao.TRADING_CRITICAL_KINDS
    assert "payments_send" in asfao.TRADING_CRITICAL_KINDS
    # Sanity: harmless kinds are NOT in the set.
    assert "telegram_alert" not in asfao.TRADING_CRITICAL_KINDS
    assert "github_issue" not in asfao.TRADING_CRITICAL_KINDS


def test_execute_action_blocks_trading_critical_defense_in_depth(asfao):
    out = asfao._execute_action({"kind": "trading_pause", "reason": "test"})
    assert out["ok"] is False
    assert out["error"] == "trading_critical_blocked"


def test_execute_action_handles_unknown_kind(asfao):
    out = asfao._execute_action({"kind": "made_up_kind_xyz"})
    assert out["ok"] is False
    assert out["error"] == "unknown_kind"


def test_execute_action_noop_short_circuits(asfao):
    out = asfao._execute_action({"kind": "noop", "recommendation": "hi", "extra": 1})
    assert out["ok"] is True
    assert out["noop"] is True
    assert out["recommendation"] == "hi"


# ---------------------------------------------------------------------------
# register_asfao + endpoints — exercise via Flask test client.
# ---------------------------------------------------------------------------


def _make_app(asfao_module, fake_bq_query):
    """Build a minimal Flask app + register asfao with a fake BQ client.

    fake_bq_query: callable(sql, job_config) -> object with .result() ->
        iterable of dicts. We capture all calls in fake_bq_query.calls.
    """
    from flask import Flask

    app = Flask(__name__)
    fake_bq = types.SimpleNamespace(query=fake_bq_query)
    fake_bigquery = sys.modules["google.cloud.bigquery"]

    asfao_module.register_asfao(
        app,
        project="test-project",
        dataset="test_dataset",
        bq_client=fake_bq,
        query_param_factory=fake_bigquery,
    )
    return app


def _capturing_query(rows_by_sql_kw=None, capture=None):
    """Build a fake bq.query that returns rows based on SQL keyword match."""
    rows_by_sql_kw = rows_by_sql_kw or {}
    capture = capture if capture is not None else []

    class _Job:
        def __init__(self, rows):
            self._rows = rows

        def result(self):
            return iter(self._rows)

    def _query(sql, job_config):
        capture.append({"sql": sql, "params": list(job_config.query_parameters or [])})
        # Pick rows by first matching keyword.
        for kw, rows in rows_by_sql_kw.items():
            if kw in sql:
                return _Job(rows)
        return _Job([])

    _query.calls = capture  # type: ignore[attr-defined]
    return _query


def test_decide_endpoint_proposes_and_persists(asfao):
    rows_map = {
        # _gather_context queries:
        "FROM `test-project.test_dataset.threat_intel`": [
            {
                "cve_id": "CVE-2026-Z",
                "severity": "CRITICAL",
                "cvss_score": 9.0,
                "affected_products": ["flask 3.1.0"],
            }
        ],
        "FROM `test-project.test_dataset.leads`": [{"n": 12}],
        "FROM `test-project.test_dataset.regional_intel_items`": [],
    }
    capture: list = []
    fake_query = _capturing_query(rows_map, capture)
    app = _make_app(asfao, fake_query)
    client = app.test_client()

    payload = {
        "synthesis": {
            "priority_actions": ["trading: collector stale 9.5h — restart signal logger"],
            "degraded_silos": ["trading"],
        },
        "synthesis_id": "syn-abc-123",
    }
    resp = client.post("/api/asfao/decide", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["proposed_count"] >= 2  # stale_collector + critical_cve + lead_nurture
    roles = {d["role"] for d in data["decisions"]}
    assert "Ops" in roles
    assert "Threat" in roles

    # Verify INSERT statements were issued — one per proposal.
    inserts = [c for c in capture if "INSERT INTO" in c["sql"]]
    assert len(inserts) == data["proposed_count"]
    # Each insert should include source_synthesis_id in the trigger blob.
    for ins in inserts:
        trigger_param = next(p for p in ins["params"] if p.name == "trigger")
        trig = json.loads(trigger_param.value)
        assert trig.get("source_synthesis_id") == "syn-abc-123"


def test_decide_endpoint_returns_zero_when_no_rules_fire(asfao):
    """Synthesis is healthy + ctx empty → no proposals."""
    fake_query = _capturing_query(rows_by_sql_kw={})
    app = _make_app(asfao, fake_query)
    client = app.test_client()
    resp = client.post("/api/asfao/decide", json={"synthesis": {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["proposed_count"] == 0
    assert data["decisions"] == []


def test_decisions_list_endpoint_filters_by_status_and_role(asfao):
    decision_rows = [
        {
            "decision_id": "d1",
            "role": "Ops",
            "trigger": {"rule": "stale_collector_issue"},
            "action": {"kind": "github_issue"},
            "confidence": 0.85,
            "status": "proposed",
            "proposed_at": datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
            "executed_at": None,
            "result": None,
        }
    ]
    rows_map = {"FROM `test-project.test_dataset.decisions`": decision_rows}
    capture: list = []
    fake_query = _capturing_query(rows_map, capture)
    app = _make_app(asfao, fake_query)
    client = app.test_client()

    resp = client.get("/api/asfao/decisions?status=proposed&role=Ops&limit=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["decision_id"] == "d1"
    assert row["role"] == "Ops"
    # datetime got serialized to ISO.
    assert isinstance(row["proposed_at"], str)
    assert "2026-05-02" in row["proposed_at"]

    # Verify the WHERE clause was constructed.
    issued = capture[-1]
    assert "status = @status" in issued["sql"]
    assert "role = @role" in issued["sql"]
    param_names = {p.name for p in issued["params"]}
    assert {"status", "role", "limit"}.issubset(param_names)


def test_execute_endpoint_blocks_without_admin_session(asfao):
    """When auth/ isn't wired, the gate falls back to 503 (admin_auth_not_configured)."""
    fake_query = _capturing_query()
    app = _make_app(asfao, fake_query)
    client = app.test_client()
    resp = client.post("/api/asfao/execute/some-id")
    # Either the wired-fallback returns 503 with admin_auth_not_configured
    # OR the auth blueprint isn't registered and we get 401. Both are OK.
    assert resp.status_code in (401, 503)
    body = resp.get_json() or {}
    assert "error" in body


def test_execute_endpoint_with_stub_admin_blocks_trading_critical(asfao, monkeypatch):
    """Patch in a permissive requires_admin to test the trading-critical refusal path."""
    # Replace auth.requires_admin via a fake module BEFORE register_asfao runs.
    fake_auth = types.ModuleType("auth")

    def _passthrough(view):
        return view

    fake_auth.requires_admin = _passthrough
    monkeypatch.setitem(sys.modules, "auth", fake_auth)

    # Stash a proposed decision with a trading-critical action.
    decision_rows = [
        {
            "decision_id": "dx",
            "role": "CTO",
            "trigger": {"rule": "trading_silo_silent"},
            "action": {"kind": "trading_pause", "reason": "test"},
            "confidence": 0.9,
            "status": "proposed",
            "proposed_at": datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
            "executed_at": None,
            "result": None,
        }
    ]
    rows_map = {"FROM `test-project.test_dataset.decisions`": decision_rows}
    fake_query = _capturing_query(rows_map)
    app = _make_app(asfao, fake_query)
    client = app.test_client()

    resp = client.post("/api/asfao/execute/dx", json={"approve": True})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "trading_critical_blocked"
    assert body["kind"] == "trading_pause"


def test_execute_endpoint_with_stub_admin_executes_safe_action(asfao, monkeypatch):
    fake_auth = types.ModuleType("auth")

    def _passthrough(view):
        return view

    fake_auth.requires_admin = _passthrough
    monkeypatch.setitem(sys.modules, "auth", fake_auth)

    decision_rows = [
        {
            "decision_id": "dy",
            "role": "Ops",
            "trigger": {"rule": "stale_collector_issue"},
            "action": {"kind": "noop", "recommendation": "fine"},
            "confidence": 0.8,
            "status": "proposed",
            "proposed_at": datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
            "executed_at": None,
            "result": None,
        }
    ]
    rows_map = {"FROM `test-project.test_dataset.decisions`": decision_rows}
    capture: list = []
    fake_query = _capturing_query(rows_map, capture)
    app = _make_app(asfao, fake_query)
    client = app.test_client()

    resp = client.post("/api/asfao/execute/dy", json={"approve": True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "executed"
    assert body["result"]["ok"] is True

    # Should have issued at least: one SELECT (load) + one UPDATE (approve)
    # + one UPDATE (executed). Rejected = same write count without exec.
    updates = [c for c in capture if "UPDATE " in c["sql"]]
    assert len(updates) >= 2


def test_execute_endpoint_rejects_when_approve_false(asfao, monkeypatch):
    fake_auth = types.ModuleType("auth")

    def _passthrough(view):
        return view

    fake_auth.requires_admin = _passthrough
    monkeypatch.setitem(sys.modules, "auth", fake_auth)

    decision_rows = [
        {
            "decision_id": "dz",
            "role": "Strategy",
            "trigger": {"rule": "regional_intel_surge"},
            "action": {"kind": "telegram_alert", "text": "..."},
            "confidence": 0.8,
            "status": "proposed",
            "proposed_at": datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
            "executed_at": None,
            "result": None,
        }
    ]
    rows_map = {"FROM `test-project.test_dataset.decisions`": decision_rows}
    fake_query = _capturing_query(rows_map)
    app = _make_app(asfao, fake_query)
    client = app.test_client()

    resp = client.post("/api/asfao/execute/dz", json={"approve": False})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "rejected"


def test_execute_endpoint_404_for_unknown_decision(asfao, monkeypatch):
    fake_auth = types.ModuleType("auth")
    fake_auth.requires_admin = lambda v: v
    monkeypatch.setitem(sys.modules, "auth", fake_auth)

    fake_query = _capturing_query(rows_by_sql_kw={})  # all empty
    app = _make_app(asfao, fake_query)
    client = app.test_client()

    resp = client.post("/api/asfao/execute/nonexistent")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"
