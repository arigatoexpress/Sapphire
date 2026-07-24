"""Tests for the Kumbaya (UniswapV3-fork) typed wrapper.

Recorded fixtures captured against MegaETH mainnet on 2026-04-30 from
`https://mainnet.megaeth.com/rpc`. No network is hit by these tests —
the StubClient pattern from Wave A's test_aave_v3.py is reused.
"""

from __future__ import annotations

import pathlib
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.megaeth.contracts.kumbaya import (
    KNOWN_FEE_TIERS,
    Q96,
    ZERO_ADDRESS,
    Kumbaya,
    KumbayaAddresses,
    PoolInfo,
    PoolState,
    QuoteResult,
    encode_path,
    sqrt_price_x96_to_price,
    tick_to_price,
)
from lib.chains.megaeth.registry import ProtocolRegistry

FIXT_DIR = pathlib.Path(__file__).parent / "fixtures" / "kumbaya"

# Mainnet addresses used in fixture capture.
WETH = "0x4200000000000000000000000000000000000006"
USDM = "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7"
USDT0 = "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"

ADDRS = KumbayaAddresses(
    factory="0x68b34591f662508076927803c567Cc8006988a09",
    quoter_v2="0x1F1a8dC7E138C34b503Ca080962aC10B75384a27",
    swap_router="0xE5BbEF8De2DB447a7432A47EBa58924d94eE470e",
)

# Pool address for WETH/USDM @ 0.3% — captured 2026-04-30.
POOL_WETH_USDM_3000 = "0x587f6eeafc7ad567e96ed1b62775fa6402164b22"


class StubClient:
    """Returns pre-staged hex responses keyed by 'to' address.

    Multi-response support: if the value is a list, it's drained in
    order across successive calls (so we can stub three sequential
    calls to the same pool — slot0, liquidity, fee).
    """

    def __init__(self, responses: dict[str, str | list[str]]) -> None:
        self.responses: dict[str, list[str]] = {}
        for k, v in responses.items():
            self.responses[k.lower()] = list(v) if isinstance(v, list) else [v]
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        if method != "eth_call":
            raise RuntimeError(f"unexpected method: {method}")
        target = params[0]["to"].lower()
        if target not in self.responses or not self.responses[target]:
            raise RuntimeError(f"no stub for {target} (call #{len(self.calls)})")
        return self.responses[target].pop(0)


# ---------------------------------------------------------------------------
# encode_path
# ---------------------------------------------------------------------------


def test_encode_path_single_hop_flat() -> None:
    encoded = encode_path([WETH, 3000, USDM])
    assert len(encoded) == 43  # 20 + 3 + 20
    assert encoded[:20].hex() == WETH[2:].lower()
    assert int.from_bytes(encoded[20:23], "big") == 3000
    assert encoded[23:].hex() == USDM[2:].lower()


def test_encode_path_single_hop_tuple_form() -> None:
    encoded_tuple = encode_path([(WETH, 3000), USDM])
    encoded_flat = encode_path([WETH, 3000, USDM])
    assert encoded_tuple == encoded_flat


def test_encode_path_multi_hop() -> None:
    encoded = encode_path([WETH, 3000, USDM, 500, USDT0])
    assert len(encoded) == 20 + 23 + 23  # 66 bytes


def test_encode_path_empty_raises() -> None:
    with pytest.raises(ValueError, match="at least one token"):
        encode_path([])


def test_encode_path_even_count_raises() -> None:
    with pytest.raises(ValueError, match="alternate"):
        encode_path([WETH, 3000])


def test_encode_path_invalid_token_raises() -> None:
    with pytest.raises(ValueError, match="invalid path token"):
        encode_path(["not-an-address", 3000, USDM])


def test_encode_path_invalid_fee_raises() -> None:
    with pytest.raises(ValueError, match="invalid fee tier"):
        encode_path([WETH, 2_000_000, USDM])


def test_encode_path_bad_tuple_shape() -> None:
    with pytest.raises(ValueError, match="path tuple must be"):
        encode_path([(WETH, 3000, USDM), USDT0])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# sqrt_price_x96_to_price + tick_to_price
# ---------------------------------------------------------------------------


def test_sqrt_price_x96_to_price_zero_returns_zero() -> None:
    assert sqrt_price_x96_to_price(0, decimals_token0=18, decimals_token1=18) == 0


def test_sqrt_price_x96_to_price_known_weth_usdm() -> None:
    # From recorded slot0: sqrt_price_x96 ≈ 3.78e30 → price ≈ 2256 USDM/WETH.
    sqrt_price = 3768705855732252830598301033836
    price = sqrt_price_x96_to_price(sqrt_price, decimals_token0=18, decimals_token1=18)
    assert 2200 < float(price) < 2350


def test_sqrt_price_x96_to_price_decimal_adjustment() -> None:
    # If token0 has more decimals than token1, the adjustment scales up.
    # Pick sqrt_price where raw_price = 1; then human price for (18, 6) = 1e12.
    sqrt_price = int(Q96)
    p_eq = sqrt_price_x96_to_price(sqrt_price, decimals_token0=18, decimals_token1=18)
    p_18_6 = sqrt_price_x96_to_price(sqrt_price, decimals_token0=18, decimals_token1=6)
    assert p_eq == Decimal(1)
    assert p_18_6 == Decimal(10) ** Decimal(12)


def test_tick_to_price_zero_tick_is_one() -> None:
    p = tick_to_price(0, decimals_token0=18, decimals_token1=18)
    assert abs(float(p) - 1.0) < 1e-9


def test_tick_to_price_negative_tick() -> None:
    # tick = -100_000 → very small price
    p = tick_to_price(-100_000, decimals_token0=18, decimals_token1=18)
    assert 0 < float(p) < 1e-3


# ---------------------------------------------------------------------------
# Kumbaya.get_pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pool_returns_address_from_factory() -> None:
    raw_hex = (FIXT_DIR / "getpool_weth_usdm_3000.hex").read_text(encoding="utf-8").strip()
    client = StubClient({ADDRS.factory: raw_hex})
    kb = Kumbaya(client, ADDRS)
    pool = await kb.get_pool(WETH, USDM, 3000)
    assert pool == POOL_WETH_USDM_3000


@pytest.mark.asyncio
async def test_get_pool_zero_address_for_missing_pair() -> None:
    encoded = "0x" + abi_encode(["address"], ["0x" + "0" * 40]).hex()
    client = StubClient({ADDRS.factory: encoded})
    kb = Kumbaya(client, ADDRS)
    pool = await kb.get_pool(WETH, USDT0, 7777)
    assert pool == ZERO_ADDRESS


@pytest.mark.asyncio
async def test_get_pool_invalid_token_raises() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid token_a"):
        await kb.get_pool("not-an-addr", USDM, 3000)


@pytest.mark.asyncio
async def test_get_pool_invalid_fee_raises() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid fee tier"):
        await kb.get_pool(WETH, USDM, 2_000_000)


# ---------------------------------------------------------------------------
# Kumbaya.quote_exact_input_single — recorded mainnet response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quote_exact_input_single_decodes_recorded_fixture() -> None:
    raw_hex = (FIXT_DIR / "quote_1weth_usdm_3000.hex").read_text(encoding="utf-8").strip()
    client = StubClient({ADDRS.quoter_v2: raw_hex})
    kb = Kumbaya(client, ADDRS)
    q = await kb.quote_exact_input_single(WETH, USDM, fee=3000, amount_in=10**18)
    assert isinstance(q, QuoteResult)
    # Recorded amount_out is ~2256 USDM (18 decimals).
    assert q.amount_out > 2000 * 10**18
    assert q.amount_out < 2400 * 10**18
    assert q.sqrt_price_x96_after > 0
    assert q.initialized_ticks_crossed >= 0
    assert q.gas_estimate > 0


@pytest.mark.asyncio
async def test_quote_exact_input_single_validates_amount_in() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="amount_in"):
        await kb.quote_exact_input_single(WETH, USDM, fee=3000, amount_in=-1)


@pytest.mark.asyncio
async def test_quote_exact_input_single_validates_sqrt_limit() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="sqrt_price_limit_x96"):
        await kb.quote_exact_input_single(
            WETH, USDM, fee=3000, amount_in=10**18, sqrt_price_limit_x96=-1
        )


@pytest.mark.asyncio
async def test_quote_exact_input_single_validates_addresses() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid token_in"):
        await kb.quote_exact_input_single("0xBAD", USDM, fee=3000, amount_in=10**18)
    with pytest.raises(ValueError, match="invalid token_out"):
        await kb.quote_exact_input_single(WETH, "0xBAD", fee=3000, amount_in=10**18)


# ---------------------------------------------------------------------------
# Kumbaya.quote_exact_input — multi-hop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quote_exact_input_synthetic_multi_hop() -> None:
    # Encode a synthetic 2-hop response:
    # (uint256 amountOut, uint160[] sqrtPricesX96After, uint32[] ticksList, uint256 gasEstimate)
    encoded = abi_encode(
        ["uint256", "uint160[]", "uint32[]", "uint256"],
        [12_345_678_900_000, [10**30, 10**30 - 100], [2, 1], 200_000],
    )
    client = StubClient({ADDRS.quoter_v2: "0x" + encoded.hex()})
    kb = Kumbaya(client, ADDRS)
    q = await kb.quote_exact_input([WETH, 3000, USDM, 500, USDT0], 10**18)
    assert q.amount_out == 12_345_678_900_000
    # The wrapper surfaces the LAST hop's sqrt + ticks for symmetry with
    # the single-hop return shape.
    assert q.sqrt_price_x96_after == 10**30 - 100
    assert q.initialized_ticks_crossed == 1
    assert q.gas_estimate == 200_000


@pytest.mark.asyncio
async def test_quote_exact_input_accepts_raw_bytes_path() -> None:
    raw_path = encode_path([WETH, 3000, USDM])
    encoded = abi_encode(
        ["uint256", "uint160[]", "uint32[]", "uint256"],
        [99_999, [10**29], [3], 100_000],
    )
    client = StubClient({ADDRS.quoter_v2: "0x" + encoded.hex()})
    kb = Kumbaya(client, ADDRS)
    q = await kb.quote_exact_input(raw_path, 10**18)
    assert q.amount_out == 99_999


@pytest.mark.asyncio
async def test_quote_exact_input_rejects_short_path() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid encoded path length"):
        await kb.quote_exact_input(b"\x00" * 10, 10**18)


@pytest.mark.asyncio
async def test_quote_exact_input_rejects_misaligned_path() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    # 20 + 22 = 42 bytes, not 20 + N*23.
    with pytest.raises(ValueError, match="invalid encoded path length"):
        await kb.quote_exact_input(b"\x00" * 42, 10**18)


@pytest.mark.asyncio
async def test_quote_exact_input_rejects_negative_amount() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="amount_in"):
        await kb.quote_exact_input(encode_path([WETH, 3000, USDM]), -1)


@pytest.mark.asyncio
async def test_quote_exact_input_rejects_unknown_path_type() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(TypeError, match="path must be"):
        await kb.quote_exact_input(123, 10**18)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Kumbaya.pool_state — recorded mainnet response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_state_decodes_recorded_fixture() -> None:
    slot0_hex = (FIXT_DIR / "pool_weth_usdm_3000_slot0.hex").read_text(encoding="utf-8").strip()
    liq_hex = (FIXT_DIR / "pool_weth_usdm_3000_liquidity.hex").read_text(encoding="utf-8").strip()
    fee_hex = (FIXT_DIR / "pool_weth_usdm_3000_fee.hex").read_text(encoding="utf-8").strip()
    client = StubClient({POOL_WETH_USDM_3000: [slot0_hex, liq_hex, fee_hex]})
    kb = Kumbaya(client, ADDRS)
    state = await kb.pool_state(POOL_WETH_USDM_3000)
    assert isinstance(state, PoolState)
    assert state.fee_pips == 3000
    assert state.sqrt_price_x96 > 0
    assert state.liquidity > 0
    assert state.unlocked is True
    # Price ~2256 USDM/WETH (both 18 decimals so raw == human).
    p = state.price_token1_per_token0()
    assert 2000 < float(p) < 2400


@pytest.mark.asyncio
async def test_pool_state_invalid_pool_address() -> None:
    kb = Kumbaya(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid pool"):
        await kb.pool_state("0xBAD")


def test_pool_state_price_zero_when_sqrt_zero() -> None:
    state = PoolState(
        sqrt_price_x96=0,
        tick=0,
        observation_index=0,
        observation_cardinality=0,
        fee_protocol=0,
        unlocked=True,
        liquidity=0,
        fee_pips=3000,
    )
    assert state.price_token1_per_token0() == Decimal(0)


# ---------------------------------------------------------------------------
# Kumbaya.top_pools_by_tvl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_top_pools_skips_zero_address_results() -> None:
    """Pairs with no pool should be filtered out."""
    zero_pool_response = "0x" + abi_encode(["address"], ["0x" + "0" * 40]).hex()
    client = StubClient(
        {
            ADDRS.factory: [zero_pool_response, zero_pool_response],
        }
    )
    kb = Kumbaya(client, ADDRS)
    candidates = [
        (WETH, USDM, 9999, "WETH/USDM 0.0?%"),
        (WETH, USDT0, 9999, "WETH/USDT0 0.0?%"),
    ]
    pools = await kb.top_pools_by_tvl(candidates)
    assert pools == []


@pytest.mark.asyncio
async def test_top_pools_skips_zero_liquidity_pools() -> None:
    """Existing pool but liquidity=0 should be filtered out."""
    pool_addr = POOL_WETH_USDM_3000
    pool_response = "0x" + abi_encode(["address"], [pool_addr]).hex()
    # slot0 = 7-tuple, liquidity = 0, fee = 3000
    slot0_resp = (
        "0x"
        + abi_encode(
            ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"],
            [10**30, 0, 0, 0, 0, 0, True],
        ).hex()
    )
    liq_resp_zero = "0x" + abi_encode(["uint128"], [0]).hex()
    fee_resp = "0x" + abi_encode(["uint24"], [3000]).hex()
    client = StubClient(
        {
            ADDRS.factory: pool_response,
            pool_addr: [slot0_resp, liq_resp_zero, fee_resp],
        }
    )
    kb = Kumbaya(client, ADDRS)
    pools = await kb.top_pools_by_tvl([(WETH, USDM, 3000, "WETH/USDM 0.3%")])
    assert pools == []


@pytest.mark.asyncio
async def test_top_pools_orders_by_liquidity_desc() -> None:
    """Two live pools should sort largest liquidity first."""
    pool_a = "0x" + "aa" * 20
    pool_b = "0x" + "bb" * 20
    pool_a_resp = "0x" + abi_encode(["address"], [pool_a]).hex()
    pool_b_resp = "0x" + abi_encode(["address"], [pool_b]).hex()
    slot0 = lambda: (  # noqa: E731
        "0x"
        + abi_encode(
            ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"],
            [10**30, 0, 0, 0, 0, 0, True],
        ).hex()
    )
    fee = lambda: "0x" + abi_encode(["uint24"], [3000]).hex()  # noqa: E731

    liq_small = "0x" + abi_encode(["uint128"], [100]).hex()
    liq_large = "0x" + abi_encode(["uint128"], [10_000]).hex()
    client = StubClient(
        {
            ADDRS.factory: [pool_a_resp, pool_b_resp],
            pool_a: [slot0(), liq_small, fee()],
            pool_b: [slot0(), liq_large, fee()],
        }
    )
    kb = Kumbaya(client, ADDRS)
    pools = await kb.top_pools_by_tvl([(WETH, USDM, 3000, "A"), (WETH, USDT0, 3000, "B")])
    assert len(pools) == 2
    assert pools[0].label == "B"  # larger liquidity sorts first
    assert pools[1].label == "A"


@pytest.mark.asyncio
async def test_top_pools_default_candidates_uses_known_set() -> None:
    """If candidates=None, the function uses the pinned default list.

    All factory calls revert (no stub) so we expect [] — this is a
    smoke test that the default list is non-empty and the iteration
    short-circuits cleanly when reads fail.
    """
    client = StubClient({})
    kb = Kumbaya(client, ADDRS)
    pools = await kb.top_pools_by_tvl()
    assert pools == []


# ---------------------------------------------------------------------------
# KumbayaAddresses + registry composition
# ---------------------------------------------------------------------------


def test_addresses_from_registry_entry() -> None:
    reg = ProtocolRegistry.from_yaml()
    e = reg.get("kumbaya")
    a = KumbayaAddresses.from_registry_entry(e)
    assert a.factory == e.address("factory")
    assert a.quoter_v2 == e.address("quoter_v2")
    assert a.swap_router == e.address("swap_router")


def test_constants_match_univ3() -> None:
    assert KNOWN_FEE_TIERS == (100, 500, 3000, 10000)
    assert ZERO_ADDRESS == "0x" + "0" * 40
    # Q96 = 2 ** 96 (use int form to avoid getcontext().prec dependence)
    assert int(Q96) == 2**96


def test_pool_info_dataclass_shape() -> None:
    p = PoolInfo(
        pool="0x" + "ab" * 20,
        token0="0x" + "11" * 20,
        token1="0x" + "22" * 20,
        fee_pips=500,
        liquidity=10**18,
        tick=12345,
        label="TestPool",
    )
    assert p.fee_pips == 500
    assert p.liquidity == 10**18
    assert p.label == "TestPool"


def test_quote_result_dataclass_shape() -> None:
    q = QuoteResult(
        amount_out=10**18,
        sqrt_price_x96_after=10**30,
        initialized_ticks_crossed=2,
        gas_estimate=150_000,
    )
    assert q.amount_out == 10**18
    assert q.gas_estimate == 150_000
