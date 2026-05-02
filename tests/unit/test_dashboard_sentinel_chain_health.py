"""Dashboard wiring for the Sentinel chain-health panel + demo poison gate.

Covers four guarantees:

1. The /chain/sentinel page renders the chain-health panel scaffold so the
   panel HTML is shipped with the build (not just bolted on at JS time).
2. The chain-health JS gracefully no-ops when ``chain_health`` is null in
   the response — the `if (!ch) { ... return; }` branch must exist so the
   blocked-flow fixture, which has no chain_health, doesn't crash the page.
3. SENTINEL_DEMO_FORCE_DEPEG=1 swaps the real gate for _PoisonGate and
   the endpoint returns severity=BLOCK + chain_state_degraded risk_flag.
4. With the env unset, the route still works — we mock default_gate() to
   return a HEALTHY verdict so the test isn't network-dependent and the
   payload contract (decision/mode/timestamp/execution_enabled) survives.
"""

from __future__ import annotations

import base64
import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def client():
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_demo_env(monkeypatch):
    """Ensure the poison-gate env flag never leaks across tests."""
    monkeypatch.delenv("SENTINEL_DEMO_FORCE_DEPEG", raising=False)
    yield


# ---------------------------------------------------------------------------
# 1. Panel HTML scaffold — the template ships with chain-health markup.
# ---------------------------------------------------------------------------


def test_sentinel_page_renders_chain_health_panel(client):
    response = client.get("/chain/sentinel", headers=_auth_header())
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # Panel scaffolding the JS targets must exist server-side.
    assert "Chain health" in html
    assert 'id="chain-health-band"' in html
    assert 'id="chain-health-pill"' in html
    assert 'id="chain-health-peg"' in html


# ---------------------------------------------------------------------------
# 2. JS hides gracefully when chain_health is null.
# ---------------------------------------------------------------------------


def test_chain_health_renderer_no_ops_when_chain_health_missing(client):
    response = client.get("/chain/sentinel", headers=_auth_header())
    html = response.get_data(as_text=True)
    # The renderer must accept null/undefined and bail before touching DOM.
    # We assert on the structural guard rather than re-reading the template
    # so a copy-tweak that breaks the contract still trips this test.
    assert "renderChainHealth" in html
    assert "if (!ch)" in html


# ---------------------------------------------------------------------------
# 3. SENTINEL_DEMO_FORCE_DEPEG=1 wires the poison gate end-to-end.
# ---------------------------------------------------------------------------


def test_demo_force_depeg_returns_block_severity(client, monkeypatch):
    monkeypatch.setenv("SENTINEL_DEMO_FORCE_DEPEG", "1")
    response = client.post(
        "/api/hackathon/sentinel/evaluate",
        json={
            "resource": "https://signals.sapphire.local/api/private-rwa-signal?basket=RH-STOCKS",
            "amount_usdc": "0.012",
            "action": "buy-private-signal",
            "payload_summary": "agent requests private RWA basket signal",
            "result_summary": "private basket risk passes issuer concentration and drawdown caps",
            "order_symbol": "PLTR",
            "notional_usd": 25,
        },
        headers=_auth_header(),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["mode"] == "policy_preview_only"
    assert body["execution_enabled"] is False
    decision = body["decision"]

    # The poison gate forces BLOCK → chain_state_degraded risk + refusal.
    assert decision["approved"] is False
    assert "chain_state_degraded" in decision["risk_flags"]
    chain_health = decision["chain_health"]
    assert chain_health is not None
    assert chain_health["severity"] == "BLOCK"
    assert chain_health["chain_id"] == 4326
    # peg_divergence_bps is normalized to a string by SentinelDecision.to_dict
    # so the wire contract stays JSON-stable across Decimal inputs.
    assert chain_health["peg_divergence_bps"] == "500"


# ---------------------------------------------------------------------------
# 4. Default behaviour — env unset, real default_gate() mocked HEALTHY.
# ---------------------------------------------------------------------------


def test_default_endpoint_contract_unchanged_when_env_unset(client, monkeypatch):
    """With SENTINEL_DEMO_FORCE_DEPEG unset, the route uses default_gate().

    We monkeypatch default_gate() to return a HEALTHY verdict so this test
    never hits the live MegaETH RPC. The contract we lock in:

      * top-level keys: execution_enabled, mode, decision, timestamp
      * decision.approved is True (default fixture is policy-clean)
      * decision.risk_flags excludes chain_state_degraded
      * decision.chain_health.severity is HEALTHY
    """
    from lib.hackathon.chain_health_gate import ChainHealthVerdict

    class _StubHealthyGate:
        def evaluate_chain(self, chain_id: int):
            return ChainHealthVerdict(
                chain_id=chain_id,
                chain_name="MegaETH",
                severity="HEALTHY",
                reasons=["test stub: chain healthy"],
            )

    # Replace default_gate at the module the route imports it from. The
    # route does ``from lib.hackathon.chain_health_gate import default_gate``
    # inside the handler each request, so patching the source module
    # guarantees the next request sees the stub.
    import lib.hackathon.chain_health_gate as gate_module

    monkeypatch.setattr(gate_module, "default_gate", lambda *a, **kw: _StubHealthyGate())

    response = client.post(
        "/api/hackathon/sentinel/evaluate",
        json={
            "resource": "https://signals.sapphire.local/api/private-rwa-signal?basket=RH-STOCKS",
            "amount_usdc": "0.012",
            "action": "buy-private-signal",
            "payload_summary": "agent requests private RWA basket signal",
            "result_summary": "private basket risk passes issuer concentration and drawdown caps",
            "order_symbol": "PLTR",
            "notional_usd": 25,
        },
        headers=_auth_header(),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert set(body.keys()) >= {"execution_enabled", "mode", "decision", "timestamp"}
    decision = body["decision"]
    assert decision["approved"] is True
    assert "chain_state_degraded" not in decision["risk_flags"]
    chain_health = decision["chain_health"]
    assert chain_health is not None
    assert chain_health["severity"] == "HEALTHY"
