"""Cross-chain Aave APY arbitrage dashboard panel: API + template + cache.

The panel surfaces ``lib.hackathon.cross_chain_alpha.scan_aave_arb`` on
``/chain/sentinel``. These tests verify the four contracts that matter for
demo + ongoing operator awareness:

1. Auth-gated like the rest of the dashboard.
2. JSON shape forwarded faithfully (signals, severities, thresholds).
3. Server-side 30s cache so 60s auto-refresh and the manual button do
   not hammer chain RPCs.
4. Template renders signals + empty state + severity badge classes the
   CSS keys on ('normal', 'opportunity', 'extreme').
"""

from __future__ import annotations

import base64
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

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


def _bust_cache() -> None:
    """Drop any prior cache entry so each test starts clean."""
    dashboard_app._cache.pop("cross_chain_aave_arb", None)
    dashboard_app._cache_time.pop("cross_chain_aave_arb", None)


@pytest.fixture
def client():
    dashboard_app.app.config["TESTING"] = True
    _bust_cache()
    with dashboard_app.app.test_client() as test_client:
        yield test_client
    _bust_cache()


# Sample payload shape mirrors lib.hackathon.cross_chain_alpha.scan_aave_arb
# (Decimals already stringified). 3 EXTREME, 2 OPPORTUNITY for the
# template render test; the API tests can use a smaller subset.
def _sample_payload(*, signal_count: int = 5) -> dict:
    severities = ["EXTREME", "EXTREME", "EXTREME", "OPPORTUNITY", "OPPORTUNITY"][:signal_count]
    spreads = ["232", "210", "205", "120", "75"][:signal_count]
    assets = ["USDC", "USDT", "WETH", "DAI", "WBTC"][:signal_count]
    signals = []
    for asset, sev, spread in zip(assets, severities, spreads, strict=True):
        signals.append(
            {
                "asset": asset,
                "severity": sev,
                "direction": f"supply on Optimism (3.50%) vs Arbitrum (1.20%) [{asset}]",
                "max_supply_spread_bps": spread,
                "max_borrow_spread_bps": "10",
                "chains": {
                    "MegaETH": {"supply_apy": "0.0480", "borrow_apy": "0.0612"},
                    "Arbitrum": {"supply_apy": "0.0120", "borrow_apy": "0.0250"},
                    "Optimism": {"supply_apy": "0.0350", "borrow_apy": "0.0498"},
                },
                "chains_unavailable": [],
            }
        )
    return {
        "top_n": 5,
        "signals": signals,
        "signal_count": len(signals),
        "max_spread_bps": spreads[0] if spreads else None,
        "thresholds": {"min_signal_spread_bps": "50", "extreme_spread_bps": "200"},
        "candidate_assets": ["USDC", "USDT", "DAI", "WETH", "WBTC"],
    }


# ── 1. Auth ─────────────────────────────────────────────────────────────


def test_arb_api_requires_auth(client):
    response = client.get("/api/cross_chain/aave_arb")
    assert response.status_code == 401


# ── 2. JSON shape forwarded ─────────────────────────────────────────────


def test_arb_api_returns_200_and_valid_shape(client):
    sample = _sample_payload(signal_count=3)
    with patch("lib.hackathon.cross_chain_alpha.scan_aave_arb", return_value=sample):
        response = client.get("/api/cross_chain/aave_arb", headers=_auth_header())

    assert response.status_code == 200
    body = response.get_json()
    assert body["signal_count"] == 3
    assert len(body["signals"]) == 3
    assert body["thresholds"]["min_signal_spread_bps"] == "50"
    assert body["thresholds"]["extreme_spread_bps"] == "200"
    # Endpoint stamps a generated_at so the panel can show "Last scan: ..."
    assert "generated_at" in body
    # Signal shape preserved end-to-end
    sig = body["signals"][0]
    assert sig["asset"] == "USDC"
    assert sig["severity"] in {"NORMAL", "OPPORTUNITY", "EXTREME"}
    assert "MegaETH" in sig["chains"]


# ── 3. 30s server-side cache ────────────────────────────────────────────


def test_arb_api_cache_hits_within_ttl(client):
    sample_a = _sample_payload(signal_count=1)
    sample_b = _sample_payload(signal_count=5)
    with patch(
        "lib.hackathon.cross_chain_alpha.scan_aave_arb",
        side_effect=[sample_a, sample_b],
    ) as mocked:
        first = client.get("/api/cross_chain/aave_arb", headers=_auth_header())
        second = client.get("/api/cross_chain/aave_arb", headers=_auth_header())

    assert first.status_code == 200
    assert second.status_code == 200
    # Second request inside the 30s window must hit the cache; scanner
    # is called exactly once even though the dashboard polls twice.
    assert mocked.call_count == 1
    assert second.get_json()["signal_count"] == first.get_json()["signal_count"]


def test_arb_api_cache_ttl_constant_is_30s():
    # The cache TTL is the load-bearing demo-day contract: 60s panel
    # auto-refresh polls the endpoint twice between scanner invocations.
    assert dashboard_app.CROSS_CHAIN_ARB_CACHE_DURATION == 30


# ── 4. Template render ──────────────────────────────────────────────────


def test_sentinel_page_renders_arb_panel_scaffold(client):
    response = client.get("/chain/sentinel", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # Header copy + offensive-alpha badge + endpoint reference
    assert "Cross-chain Aave V3 APY arbitrage" in html
    assert "offensive alpha" in html
    assert "/api/cross_chain/aave_arb" in html
    # The polling loop + manual refresh hook must be wired.
    assert "loadCrossChainArb" in html
    assert "ARB_REFRESH_MS" in html


def test_sentinel_page_includes_severity_badge_classes(client):
    # The CSS keys on three explicit severity classes; the template must
    # carry all three so the JS-built rows actually pick up styling.
    response = client.get("/chain/sentinel", headers=_auth_header())
    html = response.get_data(as_text=True)
    assert "arb-badge normal" in html or ".arb-badge.normal" in html
    assert "arb-badge.opportunity" in html or ".arb-badge.opportunity" in html
    assert "arb-badge.extreme" in html or ".arb-badge.extreme" in html


def test_sentinel_page_includes_empty_state_copy(client):
    # Equilibrium is the most common state — the demo backdrop must read
    # cleanly even when the scanner returns 0 signals.
    response = client.get("/chain/sentinel", headers=_auth_header())
    html = response.get_data(as_text=True)
    assert "No EXTREME opportunities currently" in html
    assert "chains in equilibrium" in html
    assert "Last scan" in html


# ── 5. Severity badge mapping ───────────────────────────────────────────


def test_severity_badge_classes_present_in_template(client):
    """All three severity classes (normal/opportunity/extreme) must be
    declared in the page CSS so JS-built rows render correctly."""
    response = client.get("/chain/sentinel", headers=_auth_header())
    html = response.get_data(as_text=True)
    # CSS rules
    assert ".arb-badge.normal" in html
    assert ".arb-badge.opportunity" in html
    assert ".arb-badge.extreme" in html
    # Best/worst color cues (color-coding requirement)
    assert ".arb-apy.best" in html
    assert ".arb-apy.worst" in html
