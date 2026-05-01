"""Tests for the MegaETHProtocols facade extensions added in Wave B step 2.

Covers ``stable_health``, ``peg_status``, ``is_safe_for_leverage``, and
the private ``_build_kumbaya_usdm_quote_fn`` / ``_build_aave_oracle_call_fn``
helpers that compose them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.megaeth.contracts.peg_monitor import PegBreak
from lib.chains.megaeth.contracts.usdm import USDM
from lib.chains.megaeth.protocols import MegaETHProtocols, StableHealth
from lib.chains.megaeth.registry import ProtocolRegistry

# Mainnet addresses for fixture stubbing.
USDM_TOKEN = "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7"
USDT0 = "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"
USDM_TWAP60 = "0x663B50C9DA9Bd586f855aF13e91EF2f0954c9761"
USDM_ETH_ORACLE = "0xD011778057AA740BB3703Ad4d78b3c79a1aED1cb"
KUMBAYA_QUOTER = "0x1F1a8dC7E138C34b503Ca080962aC10B75384a27"
AAVE_ORACLE = "0x421117D7319E96d831972b3F7e970bbfe29C4F21"


class StubClient:
    """eth_call multi-response router. Same shape as test_usdm.StubClient."""

    def __init__(self, responses: dict[str, list[str]]) -> None:
        self.responses: dict[str, list[str]] = {k.lower(): list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        if method != "eth_call":
            raise RuntimeError(f"unexpected method: {method}")
        target = params[0]["to"].lower()
        if target not in self.responses or not self.responses[target]:
            raise RuntimeError(f"no stub for {target} (call #{len(self.calls)})")
        return self.responses[target].pop(0)


# Pre-built encoded responses for the live-shaped fixture (TGE day data).
def _twap60_round_data(answer: int = 99_926_428) -> str:
    return (
        "0x"
        + abi_encode(
            ["uint80", "int256", "uint256", "uint256", "uint80"],
            [1, answer, 1_700_000_000, 1_700_000_060, 1],
        ).hex()
    )


def _twap60_decimals(d: int = 8) -> str:
    return "0x" + abi_encode(["uint8"], [d]).hex()


def _eth_oracle_4tuple(usd_low: int = 10**18, usd_high: int = 10**18) -> str:
    return (
        "0x"
        + abi_encode(
            ["uint256", "uint256", "uint256", "uint256"],
            [440_643_773_379_170, 440_643_773_379_170, usd_low, usd_high],
        ).hex()
    )


def _kumbaya_quote_response(out_amount: int = 999_506) -> str:
    """quoteExactInputSingle returns (uint256, uint160, uint32, uint256)."""
    return (
        "0x"
        + abi_encode(
            ["uint256", "uint160", "uint32", "uint256"],
            [out_amount, 10**30, 1, 107_870],
        ).hex()
    )


def _aave_price_response(price_8dec: int = 10**8) -> str:
    """AaveOracle.getAssetPrice(USDM) returns a uint256 at 1e8 scale."""
    return "0x" + abi_encode(["uint256"], [price_8dec]).hex()


def _erc20_total_supply(units: int) -> str:
    return "0x" + abi_encode(["uint256"], [units]).hex()


def _erc20_decimals(d: int = 18) -> str:
    return "0x" + abi_encode(["uint8"], [d]).hex()


def _erc20_balance(units: int) -> str:
    return "0x" + abi_encode(["uint256"], [units]).hex()


# ---------------------------------------------------------------------------
# _usdm dispatcher
# ---------------------------------------------------------------------------


def test_facade_usdm_dispatcher_returns_usdm_wrapper() -> None:
    proto = MegaETHProtocols(StubClient({}))
    usdm = proto._usdm()
    assert isinstance(usdm, USDM)
    assert usdm.addresses.token == USDM_TOKEN


def test_facade_usdm_dispatcher_rejects_non_stable_venue() -> None:
    """Pointing _usdm at the kumbaya entry should error — wrong category."""
    proto = MegaETHProtocols(StubClient({}))
    with pytest.raises(ValueError, match="not a stable venue"):
        proto._usdm("kumbaya")


def test_facade_usdm_dispatcher_unknown_venue_raises() -> None:
    proto = MegaETHProtocols(StubClient({}))
    with pytest.raises(KeyError, match="unknown protocol"):
        proto._usdm("nope")


# ---------------------------------------------------------------------------
# _build_kumbaya_usdm_quote_fn / _build_aave_oracle_call_fn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_kumbaya_quote_fn_returns_decimal_ratio() -> None:
    """The bound callable returns Decimal(USDT0_per_USDM) — already
    USDT0-decimal-adjusted (divide raw 6-decimal by 1e6)."""
    client = StubClient({KUMBAYA_QUOTER: [_kumbaya_quote_response(999_506)]})
    proto = MegaETHProtocols(client)
    fn = proto._build_kumbaya_usdm_quote_fn(USDM_TOKEN)
    assert fn is not None
    ratio = await fn()
    assert isinstance(ratio, Decimal)
    assert ratio == Decimal("0.999506")


@pytest.mark.asyncio
async def test_build_aave_oracle_call_fn_returns_usd_decimal() -> None:
    """The bound callable returns USD (already 1e8-scaled by AaveV3.get_asset_price)."""
    client = StubClient({AAVE_ORACLE: [_aave_price_response(10**8)]})
    proto = MegaETHProtocols(client)
    fn = proto._build_aave_oracle_call_fn(USDM_TOKEN)
    assert fn is not None
    price = await fn()
    assert price == Decimal("1.000000")


def test_build_kumbaya_quote_fn_returns_none_when_kumbaya_absent() -> None:
    """If the registry has no kumbaya entry, _build... gracefully returns None."""
    custom_reg = ProtocolRegistry({})
    proto = MegaETHProtocols(StubClient({}), registry=custom_reg)
    assert proto._build_kumbaya_usdm_quote_fn(USDM_TOKEN) is None


def test_build_aave_oracle_call_fn_returns_none_when_aave_absent() -> None:
    custom_reg = ProtocolRegistry({})
    proto = MegaETHProtocols(StubClient({}), registry=custom_reg)
    assert proto._build_aave_oracle_call_fn(USDM_TOKEN) is None


def test_build_kumbaya_quote_fn_returns_none_when_usdt0_absent() -> None:
    """Kumbaya is registered but USDT0 isn't — degrade gracefully."""
    full = ProtocolRegistry.from_yaml()
    # Strip USDT0 entry — keep aave_v3, kumbaya, usdm only.
    minimal = ProtocolRegistry({k: full.get(k) for k in ("aave_v3", "kumbaya", "usdm")})
    proto = MegaETHProtocols(StubClient({}), registry=minimal)
    assert proto._build_kumbaya_usdm_quote_fn(USDM_TOKEN) is None


# ---------------------------------------------------------------------------
# stable_health — full composition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stable_health_full_composition_healthy() -> None:
    """Wire all 4 sources; expect HEALTHY severity at the live TGE-day spread."""
    client = StubClient(
        {
            # USDM token: peg_quote (none directly), then circulating_supply (3 reads)
            #   circulating_supply: totalSupply, decimals, balanceOf x2
            #   collateral_ratio, mint_paused, redeem_paused → all None, no eth_call
            USDM_TOKEN: [
                _erc20_total_supply(360_000_000 * 10**18),
                _erc20_decimals(18),
                _erc20_balance(0),  # 0xdead
                _erc20_balance(0),  # 0x...01
            ],
            USDM_TWAP60: [_twap60_round_data(99_926_428), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(999_506)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    proto = MegaETHProtocols(client)
    health = await proto.stable_health()
    assert isinstance(health, StableHealth)
    assert health.venue == "usdm"
    assert health.severity == PegBreak.HEALTHY
    assert health.should_block_leverage is False
    assert "HEALTHY" in health.block_reason
    # The 4 sources all wired:
    assert health.peg_snapshot.sources_present == 4
    # Off-chain reads return None:
    assert health.collateral_ratio is None
    assert health.mint_open is None
    assert health.redeem_open is None
    # Circulating supply ~360M:
    assert health.circulating_supply == Decimal(360_000_000)
    # Spread well under 100bp at TGE day (live data: 7.4 bps).
    assert health.peg_snapshot.divergence_bps < Decimal(50)


@pytest.mark.asyncio
async def test_stable_health_blocks_when_severity_breaks() -> None:
    """Force a BREAK_100BP divergence — Kumbaya quote at $0.985, others $1."""
    client = StubClient(
        {
            USDM_TOKEN: [
                _erc20_total_supply(360_000_000 * 10**18),
                _erc20_decimals(18),
                _erc20_balance(0),
                _erc20_balance(0),
            ],
            USDM_TWAP60: [_twap60_round_data(100_000_000), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            # Kumbaya: 1 USDM → 0.985 USDT0. 985_000 / 10^6 = 0.985.
            KUMBAYA_QUOTER: [_kumbaya_quote_response(985_000)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    proto = MegaETHProtocols(client)
    health = await proto.stable_health()
    # 1.0 vs 0.985 = ~152 bps spread → BREAK_100BP.
    assert health.severity == PegBreak.BREAK_100BP
    assert health.should_block_leverage is True
    assert "BREAK_100BP" in health.block_reason


@pytest.mark.asyncio
async def test_stable_health_circuit_breaker_at_extreme_divergence() -> None:
    """Kumbaya at $0.80 — ~2500 bps spread → CIRCUIT_BREAKER."""
    client = StubClient(
        {
            USDM_TOKEN: [
                _erc20_total_supply(10**18),
                _erc20_decimals(18),
                _erc20_balance(0),
                _erc20_balance(0),
            ],
            USDM_TWAP60: [_twap60_round_data(100_000_000), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(800_000)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    proto = MegaETHProtocols(client)
    health = await proto.stable_health()
    assert health.severity == PegBreak.CIRCUIT_BREAKER
    assert health.should_block_leverage is True


@pytest.mark.asyncio
async def test_peg_status_returns_severity_only() -> None:
    """peg_status is the constant-time wrapper for hot loops."""
    client = StubClient(
        {
            USDM_TWAP60: [_twap60_round_data(99_926_428), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(999_506)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    proto = MegaETHProtocols(client)
    severity = await proto.peg_status()
    assert isinstance(severity, PegBreak)
    assert severity == PegBreak.HEALTHY


@pytest.mark.asyncio
async def test_is_safe_for_leverage_returns_true_when_healthy() -> None:
    client = StubClient(
        {
            USDM_TWAP60: [_twap60_round_data(99_926_428), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(999_506)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    proto = MegaETHProtocols(client)
    ok, reason = await proto.is_safe_for_leverage()
    assert ok is True
    assert reason == ""


@pytest.mark.asyncio
async def test_is_safe_for_leverage_returns_false_with_reason_on_break() -> None:
    client = StubClient(
        {
            USDM_TWAP60: [_twap60_round_data(100_000_000), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(950_000)],  # 0.95 → ~526 bps
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    proto = MegaETHProtocols(client)
    ok, reason = await proto.is_safe_for_leverage()
    assert ok is False
    assert reason  # non-empty
    # 5.26% spread → CRISIS_500BP severity.
    assert "CRISIS_500BP" in reason or "CIRCUIT_BREAKER" in reason


@pytest.mark.asyncio
async def test_is_safe_for_leverage_strategy_can_tighten_threshold() -> None:
    """A strategy that wants to refuse on WARNING (not just BREAK) can pass
    a lower min_severity_to_block.

    Two calls → two full sets of stubbed responses (each call drains
    the stub queue once; we don't share state between invocations).
    """

    def _fresh_client() -> StubClient:
        return StubClient(
            {
                USDM_TWAP60: [_twap60_round_data(100_000_000), _twap60_decimals(8)],
                USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
                # 0.997 → ~30 bps spread → WARNING_50BP.
                KUMBAYA_QUOTER: [_kumbaya_quote_response(997_000)],
                AAVE_ORACLE: [_aave_price_response(10**8)],
            }
        )

    proto1 = MegaETHProtocols(_fresh_client())
    # Default threshold (BREAK_100BP): warning passes through.
    ok, _ = await proto1.is_safe_for_leverage()
    assert ok is True
    # Tighter threshold (WARNING_50BP): warning blocks. Fresh client.
    proto2 = MegaETHProtocols(_fresh_client())
    ok, reason = await proto2.is_safe_for_leverage(min_severity_to_block=PegBreak.WARNING_50BP)
    assert ok is False
    assert "WARNING_50BP" in reason


# ---------------------------------------------------------------------------
# StableHealth dataclass
# ---------------------------------------------------------------------------


def test_stable_health_dataclass_shape() -> None:
    from lib.chains.megaeth.contracts.peg_monitor import PegSnapshot

    snap = PegSnapshot(
        usdm_kumbaya_usdt0=Decimal("0.999"),
        usdm_aave_oracle=Decimal("1.000"),
        usdm_twap60=Decimal("0.999"),
        usdm_implied_via_eth_oracle=Decimal("1.000"),
        divergence_bps=Decimal(10),
        severity=PegBreak.HEALTHY,
        sources_present=4,
    )
    h = StableHealth(
        venue="usdm",
        peg_snapshot=snap,
        collateral_ratio=None,
        mint_open=None,
        redeem_open=None,
        circulating_supply=Decimal("360_000_000"),
        severity=PegBreak.HEALTHY,
        should_block_leverage=False,
        block_reason="OK",
    )
    assert h.venue == "usdm"
    assert h.peg_snapshot.severity == PegBreak.HEALTHY
    assert h.should_block_leverage is False


# ---------------------------------------------------------------------------
# Wave A & B.1 invariance — facade extensions don't break existing methods
# ---------------------------------------------------------------------------


def test_facade_lend_overview_method_still_exists() -> None:
    proto = MegaETHProtocols(StubClient({}))
    assert hasattr(proto, "lend_overview")
    assert hasattr(proto, "quote_swap")
    assert hasattr(proto, "dex_overview")
    assert hasattr(proto, "oracle_price")


def test_facade_new_methods_present() -> None:
    proto = MegaETHProtocols(StubClient({}))
    assert hasattr(proto, "stable_health")
    assert hasattr(proto, "peg_status")
    assert hasattr(proto, "is_safe_for_leverage")


def test_registry_has_usdm_and_usdt0_entries() -> None:
    reg = ProtocolRegistry.from_yaml()
    assert "usdm" in reg
    assert "usdt0" in reg
    assert reg.get("usdm").category == "stable"
    assert reg.get("usdt0").category == "stable"
