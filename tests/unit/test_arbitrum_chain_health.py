"""Unit tests for the Arbitrum branch of the Sentinel chain-health gate.

The gate shell (PR #546, ``lib/hackathon/chain_health_gate.py``) carries
the dispatch + timeout/fail-open machinery; this module provides the
chain-specific classifier for Arbitrum One. Tests here pin the
classifier's severity rules without requiring PR #546 to be merged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from lib.hackathon.arbitrum_chain_health import (
    ARBITRUM_CHAIN_ID,
    GMX_FUNDING_BLOCK_APR,
    GMX_FUNDING_WARNING_APR,
    GMX_OI_SIZE_FLOOR_USD,
    HIGH_UTILIZATION_BLOCK_THRESHOLD,
    classify_arbitrum,
    classify_arbitrum_perps,
    evaluate_arbitrum_chain_health,
)


@dataclass
class _StubReserve:
    symbol: str
    paused: bool = False
    frozen: bool = False
    utilization: float = 0.0


@dataclass
class _StubOverview:
    reserves: list[_StubReserve]


def test_arbitrum_chain_id_is_42161() -> None:
    """Pinned because every consumer keys behaviour on this constant."""
    assert ARBITRUM_CHAIN_ID == 42161


def test_classify_arbitrum_healthy_when_all_reserves_nominal() -> None:
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="WETH", utilization=0.5),
            _StubReserve(symbol="USDC", utilization=0.7),
            _StubReserve(symbol="ARB", utilization=0.1),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == 42161
    assert verdict.chain_name == "Arbitrum One"
    assert verdict.aave_paused_reserves == []
    assert verdict.aave_frozen_reserves == []
    # Reasons list is always non-empty for downstream rendering.
    assert verdict.reasons and "nominal" in verdict.reasons[0]


def test_classify_arbitrum_warning_on_frozen_reserve() -> None:
    """Frozen reserves block new positions but allow repayment — WARNING, not BLOCK."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="WETH", frozen=True, utilization=1.0),
            _StubReserve(symbol="USDC", utilization=0.7),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "WARNING"
    assert verdict.aave_frozen_reserves == ["WETH"]
    assert verdict.aave_paused_reserves == []
    assert any("frozen" in r for r in verdict.reasons)


def test_classify_arbitrum_block_on_paused_high_utilization() -> None:
    """Paused + high-util means existing borrowers can't be liquidated — BLOCK."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="USDC", paused=True, utilization=0.95),
            _StubReserve(symbol="WETH", utilization=0.5),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert any("paused with high utilization" in r for r in verdict.reasons)


def test_classify_arbitrum_warning_when_paused_but_low_util_AND_frozen_present() -> None:
    """Paused-but-low-util shouldn't BLOCK; a coexisting frozen reserve still raises WARNING."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="rsETH", paused=True, utilization=0.0),
            _StubReserve(symbol="EURS", frozen=True, utilization=0.5),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "WARNING"
    assert "rsETH" in verdict.aave_paused_reserves
    assert "EURS" in verdict.aave_frozen_reserves


def test_classify_arbitrum_block_takes_precedence_over_warning() -> None:
    """A coexisting frozen + paused-high-util must resolve to BLOCK, not WARNING."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="USDC", paused=True, utilization=0.95),
            _StubReserve(symbol="EURS", frozen=True, utilization=0.5),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert "EURS" in verdict.aave_frozen_reserves


def test_classify_arbitrum_threshold_constant_is_80_percent() -> None:
    """Pinned: changing this changes Sentinel's payment-refusal posture."""
    assert HIGH_UTILIZATION_BLOCK_THRESHOLD == 0.80


def test_classify_arbitrum_threshold_boundary_is_strict() -> None:
    """Exactly-80% utilization paused does NOT BLOCK (strict greater-than)."""
    overview = _StubOverview(reserves=[_StubReserve(symbol="USDC", paused=True, utilization=0.80)])
    verdict = classify_arbitrum(overview)
    # paused-but-not-high-util => HEALTHY (no frozen present either)
    assert verdict.severity == "HEALTHY"


@pytest.mark.asyncio
async def test_evaluate_arbitrum_uses_arbitrum_protocols(monkeypatch: pytest.MonkeyPatch) -> None:
    """Composition path: evaluate_arbitrum_chain_health pulls ArbitrumProtocols.lend_overview."""
    captured: dict[str, object] = {}

    class FakeProtocols:
        def __init__(self, client: object) -> None:
            captured["client"] = client

        async def lend_overview(self) -> _StubOverview:
            return _StubOverview(reserves=[_StubReserve(symbol="WETH", utilization=0.4)])

    import lib.chains.arbitrum.protocols as proto_module

    monkeypatch.setattr(proto_module, "ArbitrumProtocols", FakeProtocols)

    fake_client = object()
    verdict = await evaluate_arbitrum_chain_health(fake_client)
    assert captured["client"] is fake_client
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == 42161


# =============================================================================
# GMX V2 perps tier — added by the gmx_v2 PR
# =============================================================================


@dataclass
class _StubMarket:
    name: str


@dataclass
class _StubPerpsMarketState:
    state: str
    market: _StubMarket
    funding_apr: Decimal | None = None
    oi_skew: Decimal | None = None
    oi_total_usd: Decimal | None = None


@dataclass
class _StubPerpsOverview:
    markets: list[_StubPerpsMarketState] = field(default_factory=list)


def test_gmx_thresholds_pinned() -> None:
    """Pinned constants — changing these changes Sentinel's posture on perps."""
    assert GMX_FUNDING_WARNING_APR == Decimal("2.0")
    assert GMX_FUNDING_BLOCK_APR == Decimal("5.0")
    assert GMX_OI_SIZE_FLOOR_USD == Decimal("10000000")


def test_classify_perps_healthy_when_all_markets_nominal() -> None:
    perps = _StubPerpsOverview(
        markets=[
            _StubPerpsMarketState(
                state="ok",
                market=_StubMarket("ETH-USD"),
                funding_apr=Decimal("0.05"),
                oi_skew=Decimal("0.55"),
                oi_total_usd=Decimal("100000000"),
            ),
        ]
    )
    sev, reasons, warn, block, skew = classify_arbitrum_perps(perps)
    assert sev == "HEALTHY"
    assert warn == [] and block == [] and skew == []


def test_classify_perps_warning_when_funding_apr_above_200pct() -> None:
    perps = _StubPerpsOverview(
        markets=[
            _StubPerpsMarketState(
                state="ok",
                market=_StubMarket("ALT-USD"),
                funding_apr=Decimal("3.0"),  # 300% APR
                oi_skew=Decimal("0.5"),
                oi_total_usd=Decimal("1000000"),
            ),
        ]
    )
    sev, reasons, warn, block, skew = classify_arbitrum_perps(perps)
    assert sev == "WARNING"
    assert "ALT-USD" in warn
    assert any("200%" in r for r in reasons)


def test_classify_perps_block_when_funding_apr_above_500pct() -> None:
    perps = _StubPerpsOverview(
        markets=[
            _StubPerpsMarketState(
                state="ok",
                market=_StubMarket("DEGEN-USD"),
                funding_apr=Decimal("-7.0"),  # -700% APR (shorts pay longs hard)
                oi_skew=Decimal("0.5"),
                oi_total_usd=Decimal("1000000"),
            ),
        ]
    )
    sev, reasons, warn, block, skew = classify_arbitrum_perps(perps)
    assert sev == "BLOCK"
    assert "DEGEN-USD" in block
    assert any("500%" in r for r in reasons)


def test_classify_perps_warning_on_extreme_oi_skew_with_size_floor() -> None:
    perps = _StubPerpsOverview(
        markets=[
            _StubPerpsMarketState(
                state="ok",
                market=_StubMarket("ARB-USD"),
                funding_apr=Decimal("0.10"),  # not warning on funding
                oi_skew=Decimal("0.97"),       # 97% long
                oi_total_usd=Decimal("50000000"),  # > $10M floor
            ),
        ]
    )
    sev, reasons, warn, block, skew = classify_arbitrum_perps(perps)
    assert sev == "WARNING"
    assert "ARB-USD" in skew
    assert any("one-sided" in r for r in reasons)


def test_classify_perps_skew_ignored_when_below_size_floor() -> None:
    """Tiny markets routinely run extreme skew — don't WARNING on them."""
    perps = _StubPerpsOverview(
        markets=[
            _StubPerpsMarketState(
                state="ok",
                market=_StubMarket("DUST-USD"),
                funding_apr=Decimal("0.10"),
                oi_skew=Decimal("0.99"),
                oi_total_usd=Decimal("100000"),  # $100k, below $10M floor
            ),
        ]
    )
    sev, _, _, _, skew = classify_arbitrum_perps(perps)
    assert sev == "HEALTHY"
    assert skew == []


def test_classify_perps_skips_unpriced_and_error_states() -> None:
    """States other than 'ok' are not data we can judge — skipped silently."""
    perps = _StubPerpsOverview(
        markets=[
            _StubPerpsMarketState(state="unpriced", market=_StubMarket("EXOTIC-USD")),
            _StubPerpsMarketState(
                state="error",
                market=_StubMarket("BROKE-USD"),
                funding_apr=Decimal("99"),  # would BLOCK if read
            ),
        ]
    )
    sev, _, _, _, _ = classify_arbitrum_perps(perps)
    assert sev == "HEALTHY"


def test_classify_arbitrum_combines_lend_and_perps_max_severity() -> None:
    """Final severity = max(lend, perps). WARNING (lend) + BLOCK (perps) → BLOCK."""
    lend = _StubOverview(
        reserves=[
            _StubReserve(symbol="WETH", frozen=True, utilization=0.5),  # WARNING
        ]
    )
    perps = _StubPerpsOverview(
        markets=[
            _StubPerpsMarketState(
                state="ok",
                market=_StubMarket("DEGEN"),
                funding_apr=Decimal("6.0"),  # > 500% → BLOCK
                oi_skew=Decimal("0.5"),
                oi_total_usd=Decimal("1000"),
            ),
        ]
    )
    verdict = classify_arbitrum(lend, perps=perps)
    assert verdict.severity == "BLOCK"
    assert "WETH" in verdict.aave_frozen_reserves
    assert "DEGEN" in verdict.gmx_funding_block_markets


def test_classify_arbitrum_perps_argument_is_optional_for_back_compat() -> None:
    """Old call shape classify_arbitrum(lend) keeps working unchanged."""
    lend = _StubOverview(reserves=[_StubReserve(symbol="WETH", utilization=0.5)])
    verdict = classify_arbitrum(lend)
    assert verdict.severity == "HEALTHY"
    assert verdict.gmx_funding_warning_markets == []
    assert verdict.gmx_funding_block_markets == []
    assert verdict.gmx_skewed_markets == []


@pytest.mark.asyncio
async def test_evaluate_with_perps_includes_gmx_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evaluator pulls perps_overview() and folds it into the verdict."""

    class FakeProtocols:
        def __init__(self, client: object) -> None:
            pass

        async def lend_overview(self) -> _StubOverview:
            return _StubOverview(reserves=[_StubReserve(symbol="WETH", utilization=0.4)])

        async def perps_overview(self) -> _StubPerpsOverview:
            return _StubPerpsOverview(
                markets=[
                    _StubPerpsMarketState(
                        state="ok",
                        market=_StubMarket("DEGEN"),
                        funding_apr=Decimal("6.0"),
                        oi_skew=Decimal("0.5"),
                        oi_total_usd=Decimal("1000"),
                    ),
                ]
            )

    import lib.chains.arbitrum.protocols as proto_module

    monkeypatch.setattr(proto_module, "ArbitrumProtocols", FakeProtocols)

    verdict = await evaluate_arbitrum_chain_health(object())
    assert verdict.severity == "BLOCK"
    assert "DEGEN" in verdict.gmx_funding_block_markets


@pytest.mark.asyncio
async def test_evaluate_soft_fails_perps_on_rpc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient GMX RPC failure must NOT silently fail-closed the verdict."""

    class FakeProtocols:
        def __init__(self, client: object) -> None:
            pass

        async def lend_overview(self) -> _StubOverview:
            return _StubOverview(reserves=[_StubReserve(symbol="WETH", utilization=0.4)])

        async def perps_overview(self) -> _StubPerpsOverview:
            raise RuntimeError("gmx-rpc-down")

    import lib.chains.arbitrum.protocols as proto_module

    monkeypatch.setattr(proto_module, "ArbitrumProtocols", FakeProtocols)

    verdict = await evaluate_arbitrum_chain_health(object())
    # Lend was healthy; perps soft-failed → final HEALTHY (no escalation).
    assert verdict.severity == "HEALTHY"
    assert verdict.gmx_funding_block_markets == []
