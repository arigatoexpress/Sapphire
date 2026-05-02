"""Dashboard wiring for SENTINEL_DEMO_FORCE_INJECTION demo toggle.

Lane R (PR #560) recommended that the London Buildathon demo opener
should be the prompt-injection-blocked-AND-anchored beat — visceral
30-second story: "Cryptographic attack attestation anchored on the
chain Robinhood operates."

This module mirrors test_dashboard_sentinel_chain_health.py (Lane E,
PR #555) and locks in the following guarantees:

1. SENTINEL_DEMO_FORCE_INJECTION=1 mutates the inbound payload so the
   existing prompt-injection screen rejects the payment naturally and
   a chain-anchor receipt is still populated.
2. With the env var unset, the route preserves the existing behavior
   (mocked-healthy gate; default fixture stays approved).
3. Combined SENTINEL_DEMO_FORCE_INJECTION=1 + SENTINEL_DEMO_FORCE_DEPEG=1
   surfaces BOTH risk reasons stacked (injection + chain_state_degraded).
4. The secret-egress screen also fires alongside prompt-injection (we
   bury an OPENAI_API_KEY / BEGIN PRIVATE KEY pattern in result_summary).
5. The Policy screening panel HTML renders the BLOCKED beat scaffold
   so judges see prompt-injection + secret-egress + on-chain anchor.

Plus a deterministic-mutation pytest verifying _inject_synthetic_attack
returns the same shape across calls (so demo runs are reproducible).
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
    """Ensure neither demo env flag leaks across tests."""
    monkeypatch.delenv("SENTINEL_DEMO_FORCE_INJECTION", raising=False)
    monkeypatch.delenv("SENTINEL_DEMO_FORCE_DEPEG", raising=False)
    yield


@pytest.fixture
def _stub_healthy_gate(monkeypatch):
    """Replace default_gate() with a HEALTHY stub so tests are network-free."""
    from lib.hackathon.chain_health_gate import ChainHealthVerdict
    import lib.hackathon.chain_health_gate as gate_module

    class _StubHealthyGate:
        def evaluate_chain(self, chain_id: int):
            return ChainHealthVerdict(
                chain_id=chain_id,
                chain_name="MegaETH",
                severity="HEALTHY",
                reasons=["test stub: chain healthy"],
            )

    monkeypatch.setattr(
        gate_module, "default_gate", lambda *a, **kw: _StubHealthyGate()
    )


_BASELINE_PAYLOAD = {
    "resource": "https://signals.sapphire.local/api/private-rwa-signal?basket=RH-STOCKS",
    "amount_usdc": "0.012",
    "action": "buy-private-signal",
    "payload_summary": "agent requests private RWA basket signal",
    "result_summary": "private basket risk passes issuer concentration and drawdown caps",
    "order_symbol": "PLTR",
    "notional_usd": 25,
}


# ---------------------------------------------------------------------------
# 1. SENTINEL_DEMO_FORCE_INJECTION=1 wires the synthetic attack end-to-end.
# ---------------------------------------------------------------------------


def test_demo_force_injection_blocks_and_surfaces_anchor(
    client, monkeypatch, _stub_healthy_gate
):
    """The injection toggle must produce: approved=False, prompt_injection
    flag set, and a populated chain-anchor receipt (the demo beat)."""
    monkeypatch.setenv("SENTINEL_DEMO_FORCE_INJECTION", "1")
    response = client.post(
        "/api/hackathon/sentinel/evaluate",
        json=dict(_BASELINE_PAYLOAD),
        headers=_auth_header(),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["mode"] == "policy_preview_only"
    assert body["execution_enabled"] is False
    decision = body["decision"]

    # Existing prompt-injection screen rejects naturally.
    assert decision["approved"] is False
    assert "prompt_injection" in decision["risk_flags"]

    # Reasons surface a human-readable injection explanation.
    reasons_blob = " ".join(decision["reasons"]).lower()
    assert "prompt-injection" in reasons_blob

    # The anchor is still populated — even rejected attacks get a receipt.
    anchor = decision["chain_anchor"]
    assert anchor is not None
    assert anchor["receipt_id"].startswith("0x")
    assert len(anchor["receipt_id"]) == 66
    assert anchor["approved"] is False
    assert anchor["chain"] == "robinhood_testnet"
    assert anchor["contract"] == "SapphireSentinelRegistry"


# ---------------------------------------------------------------------------
# 2. Env unset → existing behavior preserved (no injection-mutation).
# ---------------------------------------------------------------------------


def test_default_endpoint_unchanged_when_injection_env_unset(
    client, _stub_healthy_gate
):
    """Without SENTINEL_DEMO_FORCE_INJECTION, the default policy-clean
    fixture must stay approved (the existing depeg-test contract)."""
    response = client.post(
        "/api/hackathon/sentinel/evaluate",
        json=dict(_BASELINE_PAYLOAD),
        headers=_auth_header(),
    )
    assert response.status_code == 200
    body = response.get_json()
    decision = body["decision"]
    assert decision["approved"] is True
    assert "prompt_injection" not in decision["risk_flags"]
    assert "secret_egress_risk" not in decision["risk_flags"]


# ---------------------------------------------------------------------------
# 3. Combined toggles → BOTH reasons stack.
# ---------------------------------------------------------------------------


def test_combined_injection_and_depeg_returns_both_reasons(client, monkeypatch):
    """When both demo flags are set, the response must surface BOTH the
    chain_state_degraded reason AND the prompt_injection reason. This is
    the worst-case demo: the chain is degrading AND the agent is being
    actively attacked. Sentinel refuses for both reasons, and both
    receipts (chain-health verdict + on-chain anchor) anchor on Robinhood
    Chain so judges see the full attack-attestation surface."""
    monkeypatch.setenv("SENTINEL_DEMO_FORCE_INJECTION", "1")
    monkeypatch.setenv("SENTINEL_DEMO_FORCE_DEPEG", "1")
    response = client.post(
        "/api/hackathon/sentinel/evaluate",
        json=dict(_BASELINE_PAYLOAD),
        headers=_auth_header(),
    )
    assert response.status_code == 200
    body = response.get_json()
    decision = body["decision"]

    assert decision["approved"] is False
    assert "prompt_injection" in decision["risk_flags"]
    assert "chain_state_degraded" in decision["risk_flags"]

    chain_health = decision["chain_health"]
    assert chain_health is not None
    assert chain_health["severity"] == "BLOCK"

    # The chain-anchor still carries a receipt_id even though the payment
    # is refused — this is the visceral demo beat.
    anchor = decision["chain_anchor"]
    assert anchor["approved"] is False
    assert anchor["receipt_id"].startswith("0x")


# ---------------------------------------------------------------------------
# 4. Secret-egress screen also trips alongside prompt-injection.
# ---------------------------------------------------------------------------


def test_demo_force_injection_also_trips_secret_egress(
    client, monkeypatch, _stub_healthy_gate
):
    """The synthetic attack buries OPENAI_API_KEY + BEGIN PRIVATE KEY in
    result_summary so the secret-egress screen fires alongside the
    prompt-injection screen — judges see Sentinel catch a
    multi-vector attack in one pass."""
    monkeypatch.setenv("SENTINEL_DEMO_FORCE_INJECTION", "1")
    response = client.post(
        "/api/hackathon/sentinel/evaluate",
        json=dict(_BASELINE_PAYLOAD),
        headers=_auth_header(),
    )
    assert response.status_code == 200
    body = response.get_json()
    decision = body["decision"]
    assert "secret_egress_risk" in decision["risk_flags"]
    # At least one secret pattern is enumerated in redactions.
    redactions = decision["redactions"]
    assert len(redactions) > 0
    secret_patterns = {
        "api_key",
        "apikey",
        "private_key",
        "secret",
        "seed phrase",
        "mnemonic",
        "telegram_bot_token",
        "robinhood_ed25519",
    }
    assert any(r in secret_patterns for r in redactions)


# ---------------------------------------------------------------------------
# 5. Panel HTML scaffold ships the BLOCKED beat.
# ---------------------------------------------------------------------------


def test_sentinel_page_renders_policy_screening_panel(client):
    """The /chain/sentinel page must ship the Policy screening panel
    scaffold (band + pill + injection/secrets/anchor rows) and the
    renderScreening() JS guard. Asserting on structure rather than
    re-templating so a copy-tweak that breaks the contract trips."""
    response = client.get("/chain/sentinel", headers=_auth_header())
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Policy screening" in html
    assert 'id="screening-band"' in html
    assert 'id="screening-pill"' in html
    assert 'id="screening-injection"' in html
    assert 'id="screening-secrets"' in html
    assert 'id="screening-anchor"' in html
    # The renderScreening guard must exist so tests are independent of JS.
    assert "renderScreening" in html


# ---------------------------------------------------------------------------
# 6. _inject_synthetic_attack mutation is deterministic + non-destructive.
# ---------------------------------------------------------------------------


def test_inject_synthetic_attack_mutation_is_deterministic():
    """Two calls with the same input must produce equal output — the demo
    relies on reproducible hashes (risk_hash / receipt_id / result_hash)
    so Lane R can rehearse the beat and confirm the on-chain anchor
    receipt looks identical across runs."""
    base = dict(_BASELINE_PAYLOAD)
    a = dashboard_app._inject_synthetic_attack(base)
    b = dashboard_app._inject_synthetic_attack(base)
    assert a == b
    # Original dict is not mutated in place — repeat calls stay safe.
    assert base["payload_summary"] == _BASELINE_PAYLOAD["payload_summary"]
    assert base["result_summary"] == _BASELINE_PAYLOAD["result_summary"]
    # Mutated copy contains the canonical injection patterns.
    assert "ignore all previous instructions" in a["payload_summary"].lower()
    assert "private key" in a["result_summary"].lower()
    assert "api_key" in a["result_summary"].lower() or "openai_api_key" in a["result_summary"].lower()
