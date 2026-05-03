"""GMX V2 perps dashboard panel: API + template + cache + scanner.

Mirrors ``tests/unit/test_dashboard_cross_chain_arb_panel.py`` for the
companion perps panel. The panel surfaces
:func:`lib.perps.gmx_v2_overview.scan_perps_overview` on
``/chain/sentinel``. These tests verify the contracts that matter for
demo + ongoing operator awareness:

1. Auth-gated like the rest of the dashboard.
2. JSON shape forwarded faithfully (markets, severities, divergence,
   thresholds, mode tag).
3. Server-side 30s cache so 60s auto-refresh and the manual button do
   not hammer chain RPCs.
4. Template renders the panel + empty state + severity badge classes
   the CSS keys on ('normal', 'warn', 'extreme').
5. Severity classification math (the load-bearing demo-day signal).
6. Cross-chain funding divergence pairing logic.
"""

from __future__ import annotations

import base64
import importlib
import os
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")

from lib.perps.gmx_v2_overview import (  # noqa: E402
    EXTREME_FUNDING_ABS_APR,
    EXTREME_SKEW_DELTA,
    WARN_FUNDING_ABS_APR,
    PerpsMarketSnapshot,
    _classify_severity,
    _side_recommendation,
    compute_cross_chain_divergence,
    is_integration_enabled,
    scan_perps_overview,
)


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


def _bust_cache() -> None:
    """Drop any prior cache entry so each test starts clean."""
    dashboard_app._cache.pop("perps_overview", None)
    dashboard_app._cache_time.pop("perps_overview", None)


@pytest.fixture
def client():
    dashboard_app.app.config["TESTING"] = True
    _bust_cache()
    with dashboard_app.app.test_client() as test_client:
        yield test_client
    _bust_cache()


def _sample_payload(*, market_count: int = 4) -> dict:
    """Build a payload mirroring scan_perps_overview()'s sample mode."""
    markets = [
        {
            "chain_id": 4326,
            "chain_name": "MegaETH",
            "market_name": "ETH/USD MegaETH 0.3%",
            "market_address": "0xee" + "0" * 38,
            "funding_apr": "0.5612",
            "funding_direction": "longs_pay_shorts",
            "open_interest_long_usd": "8425000",
            "open_interest_short_usd": "1860000",
            "skew": "0.819",
            "mark_price_usd": "3142.55",
            "severity": "EXTREME",
            "side_recommendation": "short collects funding",
        },
        {
            "chain_id": 4326,
            "chain_name": "MegaETH",
            "market_name": "BTC/USD MegaETH 0.3%",
            "market_address": "0xbb" + "0" * 38,
            "funding_apr": "-0.4318",
            "funding_direction": "shorts_pay_longs",
            "open_interest_long_usd": "1240000",
            "open_interest_short_usd": "4905000",
            "skew": "0.202",
            "mark_price_usd": "76812.40",
            "severity": "EXTREME",
            "side_recommendation": "long collects funding",
        },
        {
            "chain_id": 42161,
            "chain_name": "Arbitrum",
            "market_name": "ETH/USD Arbitrum",
            "market_address": "0xea" + "0" * 38,
            "funding_apr": "0.0213",
            "funding_direction": "longs_pay_shorts",
            "open_interest_long_usd": "142500000",
            "open_interest_short_usd": "128300000",
            "skew": "0.526",
            "mark_price_usd": "3140.18",
            "severity": "NORMAL",
            "side_recommendation": "short collects funding",
        },
        {
            "chain_id": 42161,
            "chain_name": "Arbitrum",
            "market_name": "BTC/USD Arbitrum",
            "market_address": "0xba" + "0" * 38,
            "funding_apr": "-0.1502",
            "funding_direction": "shorts_pay_longs",
            "open_interest_long_usd": "82400000",
            "open_interest_short_usd": "106700000",
            "skew": "0.436",
            "mark_price_usd": "76798.91",
            "severity": "WARN",
            "side_recommendation": "long collects funding",
        },
    ][:market_count]
    by_chain: dict[str, list[dict]] = {}
    for m in markets:
        by_chain.setdefault(str(m["chain_id"]), []).append(m)
    return {
        "mode": "sample",
        "markets": markets,
        "by_chain": by_chain,
        "chain_names": {4326: "MegaETH", 42161: "Arbitrum"},
        "cross_chain_funding_divergence": [
            {
                "underlying": "ETH",
                "chain_a": "MegaETH",
                "chain_b": "Arbitrum",
                "apr_a": "0.5612",
                "apr_b": "0.0213",
                "divergence_bps": "5399.0000",
            },
            {
                "underlying": "BTC",
                "chain_a": "MegaETH",
                "chain_b": "Arbitrum",
                "apr_a": "-0.4318",
                "apr_b": "-0.1502",
                "divergence_bps": "-2816.0000",
            },
        ],
        "max_abs_divergence_bps": "5399.0000",
        "extreme_count": sum(1 for m in markets if m["severity"] == "EXTREME"),
        "wiring_errors": [],
        "thresholds": {
            "extreme_funding_abs_apr": "0.50",
            "warn_funding_abs_apr": "0.20",
            "extreme_skew_delta": "0.20",
        },
    }


# ── 1. Auth ─────────────────────────────────────────────────────────────


def test_perps_api_requires_auth(client):
    response = client.get("/api/perps/overview")
    assert response.status_code == 401


# ── 2. JSON shape forwarded ─────────────────────────────────────────────


def test_perps_api_returns_200_and_valid_shape(client):
    sample = _sample_payload()
    with patch("lib.perps.gmx_v2_overview.scan_perps_overview", return_value=sample):
        response = client.get("/api/perps/overview", headers=_auth_header())

    assert response.status_code == 200
    body = response.get_json()
    # Shape contract
    assert body["mode"] in {"live", "sample", "empty"}
    assert isinstance(body["markets"], list)
    assert len(body["markets"]) == 4
    assert "by_chain" in body
    assert "4326" in body["by_chain"]
    assert "42161" in body["by_chain"]
    assert isinstance(body["cross_chain_funding_divergence"], list)
    assert body["thresholds"]["extreme_funding_abs_apr"] == "0.50"
    assert body["thresholds"]["warn_funding_abs_apr"] == "0.20"
    # Endpoint stamps a generated_at so the panel can show "Last refresh: ..."
    assert "generated_at" in body
    # First market has the full snapshot shape
    m = body["markets"][0]
    for k in (
        "chain_id",
        "chain_name",
        "market_name",
        "market_address",
        "funding_apr",
        "funding_direction",
        "open_interest_long_usd",
        "open_interest_short_usd",
        "skew",
        "severity",
        "side_recommendation",
    ):
        assert k in m, f"missing {k}"
    assert m["severity"] in {"NORMAL", "WARN", "EXTREME"}


def test_perps_api_includes_extreme_funding_signal(client):
    """The BTC/ETH funding divergence is the load-bearing demo signal."""
    sample = _sample_payload()
    with patch("lib.perps.gmx_v2_overview.scan_perps_overview", return_value=sample):
        response = client.get("/api/perps/overview", headers=_auth_header())
    body = response.get_json()
    # Both BTC and ETH same-underlying divergences should be present.
    by_underlying = {d["underlying"]: d for d in body["cross_chain_funding_divergence"]}
    assert "ETH" in by_underlying
    assert "BTC" in by_underlying
    # ETH MegaETH (+56%) vs Arbitrum (+2%) = +5,399 bps divergence
    eth_div = float(by_underlying["ETH"]["divergence_bps"])
    assert 5300 < eth_div < 5500


# ── 3. 30s server-side cache ────────────────────────────────────────────


def test_perps_api_cache_hits_within_ttl(client):
    sample_a = _sample_payload(market_count=2)
    sample_b = _sample_payload(market_count=4)
    with patch(
        "lib.perps.gmx_v2_overview.scan_perps_overview",
        side_effect=[sample_a, sample_b],
    ) as mocked:
        first = client.get("/api/perps/overview", headers=_auth_header())
        second = client.get("/api/perps/overview", headers=_auth_header())

    assert first.status_code == 200
    assert second.status_code == 200
    # Second request inside the 30s window must hit the cache; scanner
    # is called exactly once even though the dashboard polls twice.
    assert mocked.call_count == 1
    assert len(second.get_json()["markets"]) == len(first.get_json()["markets"])


def test_perps_api_cache_ttl_constant_is_30s():
    # The cache TTL is the load-bearing demo-day contract: 60s panel
    # auto-refresh polls the endpoint twice between scanner invocations.
    assert dashboard_app.PERPS_OVERVIEW_CACHE_DURATION == 30


# ── 4. Template render ──────────────────────────────────────────────────


def test_sentinel_page_renders_perps_panel_scaffold(client):
    response = client.get("/chain/sentinel", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # Header copy + offensive-alpha badge + endpoint reference
    assert "GMX V2 perps" in html
    assert "/api/perps/overview" in html
    # The polling loop + manual refresh hook must be wired.
    assert "loadPerpsOverview" in html
    assert "PERPS_REFRESH_MS" in html


def test_sentinel_page_includes_perps_severity_badge_classes(client):
    """Three explicit severity classes; template carries all so JS-built
    rows actually pick up styling."""
    response = client.get("/chain/sentinel", headers=_auth_header())
    html = response.get_data(as_text=True)
    assert ".perps-badge.normal" in html
    assert ".perps-badge.warn" in html
    assert ".perps-badge.extreme" in html


def test_sentinel_page_includes_perps_empty_state_copy(client):
    """Empty state must read cleanly when both chains return no markets."""
    response = client.get("/chain/sentinel", headers=_auth_header())
    html = response.get_data(as_text=True)
    assert "No priced perps markets currently" in html
    assert "both chains returned empty" in html


def test_sentinel_page_includes_perps_funding_color_classes(client):
    """Color-coded APR cells need extreme-pos/extreme-neg classes for
    JS-built rows to render correctly."""
    response = client.get("/chain/sentinel", headers=_auth_header())
    html = response.get_data(as_text=True)
    assert ".perps-funding.extreme-pos" in html
    assert ".perps-funding.extreme-neg" in html
    assert ".perps-funding.warn-pos" in html
    assert ".perps-funding.warn-neg" in html
    # Skew color cues
    assert ".perps-skew.extreme" in html


# ── 5. Severity badge color mapping (scanner-side) ───────────────────────


def test_severity_extreme_when_funding_apr_above_50pct():
    assert _classify_severity(Decimal("0.55"), Decimal("0.5")) == "EXTREME"
    assert _classify_severity(Decimal("-0.55"), Decimal("0.5")) == "EXTREME"


def test_severity_extreme_when_skew_outside_30_70_band():
    assert _classify_severity(Decimal("0.0"), Decimal("0.75")) == "EXTREME"
    assert _classify_severity(Decimal("0.0"), Decimal("0.25")) == "EXTREME"


def test_severity_warn_at_intermediate_funding():
    assert _classify_severity(Decimal("0.30"), Decimal("0.5")) == "WARN"
    assert _classify_severity(Decimal("-0.30"), Decimal("0.5")) == "WARN"


def test_severity_normal_when_balanced():
    assert _classify_severity(Decimal("0.05"), Decimal("0.5")) == "NORMAL"
    assert _classify_severity(Decimal("0.0"), Decimal("0.5")) == "NORMAL"


def test_side_recommendation_directional_flip():
    assert "short collects" in _side_recommendation(Decimal("0.10"))
    assert "long collects" in _side_recommendation(Decimal("-0.10"))
    assert "balanced" in _side_recommendation(Decimal("0"))


def test_thresholds_match_demo_contract():
    # The thresholds are the load-bearing demo signal: anything past
    # ±50% APR should pop as EXTREME so judges can't miss it.
    assert EXTREME_FUNDING_ABS_APR == Decimal("0.50")
    assert WARN_FUNDING_ABS_APR == Decimal("0.20")
    assert EXTREME_SKEW_DELTA == Decimal("0.20")


# ── 6. Cross-chain divergence pairing ────────────────────────────────────


def _snap(
    chain_id: int, name: str, market_name: str, apr: str, skew: str = "0.5"
) -> PerpsMarketSnapshot:
    return PerpsMarketSnapshot(
        chain_id=chain_id,
        chain_name=name,
        market_name=market_name,
        market_address="0x" + "0" * 40,
        funding_apr=Decimal(apr),
        funding_direction="longs_pay_shorts" if Decimal(apr) >= 0 else "shorts_pay_longs",
        open_interest_long_usd=Decimal("100"),
        open_interest_short_usd=Decimal("100"),
        skew=Decimal(skew),
        mark_price_usd=Decimal("100"),
        severity="NORMAL",
        side_recommendation="balanced — no funding edge",
    )


def test_cross_chain_divergence_pairs_same_underlying():
    snaps = [
        _snap(4326, "MegaETH", "ETH/USD MegaETH 0.3%", "0.50"),
        _snap(42161, "Arbitrum", "ETH/USD Arbitrum", "0.02"),
    ]
    divs = compute_cross_chain_divergence(snaps)
    assert len(divs) == 1
    eth_div = divs[0]
    assert eth_div.underlying == "ETH"
    # 0.50 - 0.02 = 0.48 → 4800 bps
    assert eth_div.divergence_bps == Decimal("4800.0000")


def test_cross_chain_divergence_skips_unmatched_chains():
    snaps = [
        _snap(4326, "MegaETH", "SOL/USD MegaETH 0.3%", "0.50"),
        _snap(42161, "Arbitrum", "ETH/USD Arbitrum", "0.02"),
    ]
    # No same-underlying overlap — return empty.
    assert compute_cross_chain_divergence(snaps) == []


# ── 7. Empty / sample mode ───────────────────────────────────────────────


def test_scanner_force_sample_returns_sample_mode():
    out = scan_perps_overview(force_sample=True)
    assert out["mode"] == "sample"
    assert len(out["markets"]) >= 4
    # Sample is calibrated to the demo: 2 EXTREME (BTC/ETH on MegaETH).
    assert out["extreme_count"] == 2


def test_scanner_with_injected_snapshots_is_live_mode():
    snaps = [
        _snap(4326, "MegaETH", "WETH/USD MegaETH", "0.10"),
    ]
    out = scan_perps_overview(snapshots=snaps)
    assert out["mode"] == "live"
    assert len(out["markets"]) == 1


# ── 8. Gated integration test against live mainnets ──────────────────────


@pytest.mark.skipif(
    not is_integration_enabled(),
    reason="set SAPPHIRE_PERPS_INTEGRATION=1 for live MegaETH+Arbitrum scan",
)
def test_perps_overview_live_integration():
    """End-to-end: scanner pulls from live GMX V2 contracts on both chains.

    Gated by env so it doesn't run in default CI. When live wrappers
    are not yet shipped on this branch the scanner gracefully falls
    back to the sample payload — that's still a useful smoke test
    (the payload is well-formed and the divergence math runs).
    """
    out = scan_perps_overview()
    assert out["mode"] in {"live", "sample"}
    # Either way the structural contract holds.
    assert isinstance(out["markets"], list)
    assert isinstance(out["cross_chain_funding_divergence"], list)
    assert "thresholds" in out
