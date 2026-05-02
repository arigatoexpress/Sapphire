"""Wave B step 1 facade tests — DEX-spot extensions.

Wave A's existing test_protocols_facade.py covers the lend_* surface.
This file covers the new ``quote_swap`` and ``dex_overview`` methods
plus the DexRoutingTable composition. Kept separate so a developer
checking what Wave B added can read it in isolation.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.megaeth.contracts.kumbaya import (
    KumbayaAddresses,
    PoolInfo,
)
from lib.chains.megaeth.dex_router import SwapQuote
from lib.chains.megaeth.protocols import (
    DexOverview,
    DexVenueOverview,
    MegaETHProtocols,
)
from lib.chains.megaeth.registry import ProtocolEntry, ProtocolRegistry

FIXT_DIR = pathlib.Path(__file__).parent / "fixtures" / "kumbaya"

WETH = "0x4200000000000000000000000000000000000006"
USDM = "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7"

KUMBAYA_FACTORY = "0x68b34591f662508076927803c567Cc8006988a09"
KUMBAYA_QUOTER = "0x1F1a8dC7E138C34b503Ca080962aC10B75384a27"


class StubClient:
    """Same multi-response StubClient as test_kumbaya.py."""

    def __init__(self, responses: dict[str, str | list[str]]) -> None:
        self.responses: dict[str, list[str]] = {}
        for k, v in responses.items():
            self.responses[k.lower()] = list(v) if isinstance(v, list) else [v]
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        target = params[0]["to"].lower()
        if target not in self.responses or not self.responses[target]:
            raise RuntimeError(f"no stub for {target}")
        return self.responses[target].pop(0)


@pytest.mark.asyncio
async def test_quote_swap_returns_kumbaya_quote_for_known_pair() -> None:
    """quote_swap routes to Kumbaya and returns the best fee tier."""
    quote_hex = (FIXT_DIR / "quote_1weth_usdm_3000.hex").read_text().strip()
    # The router probes 4 fee tiers — stub all 4 with the same response so
    # the fixture returns a usable QuoteResult on each call. The router
    # picks the one with highest amount_out (all equal here, returns first).
    client = StubClient({KUMBAYA_QUOTER: [quote_hex] * 4})
    proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
    quote = await proto.quote_swap(WETH, USDM, 10**18)
    assert quote is not None
    assert isinstance(quote, SwapQuote)
    assert quote.venue == "kumbaya"
    assert quote.amount_out > 2000 * 10**18
    assert quote.hops == 1


@pytest.mark.asyncio
async def test_quote_swap_returns_none_when_all_tiers_fail() -> None:
    """No quoter stub → every fee tier reverts → quote_swap returns None."""
    client = StubClient({})
    proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
    quote = await proto.quote_swap(WETH, USDM, 10**18)
    assert quote is None


@pytest.mark.asyncio
async def test_quote_swap_with_no_dexes_registered_returns_none() -> None:
    """quote_swap with a registry that has no dex_spot entries → None."""
    aave_only = ProtocolEntry(
        key="aave_v3",
        name="Aave V3",
        category="lending",
        priority=1,
        status="active",
        docs_url="",
        addresses={
            "pool": "0x" + "1" * 40,
            "pool_addresses_provider": "0x" + "2" * 40,
            "oracle": "0x" + "3" * 40,
            "ui_pool_data_provider": "0x" + "4" * 40,
            "protocol_data_provider": "0x" + "5" * 40,
        },
        abi_paths={},
    )
    reg = ProtocolRegistry({"aave_v3": aave_only})
    proto = MegaETHProtocols(client=StubClient({}), registry=reg)
    quote = await proto.quote_swap(WETH, USDM, 10**18)
    assert quote is None


@pytest.mark.asyncio
async def test_quote_swap_invalid_max_hops_raises() -> None:
    proto = MegaETHProtocols(client=StubClient({}))
    with pytest.raises(ValueError, match="max_hops must be"):
        await proto.quote_swap(WETH, USDM, 10**18, max_hops=0)


@pytest.mark.asyncio
async def test_dex_overview_lists_kumbaya_with_top_pools() -> None:
    """dex_overview returns one venue (kumbaya) with pool info.

    We stub all factory.getPool calls to return a single fake pool, and
    every pool_state read to return non-zero liquidity, so the overview
    surfaces non-empty top_pools.
    """
    fake_pool = "0x" + "ab" * 20
    pool_resp = "0x" + abi_encode(["address"], [fake_pool]).hex()
    slot0_resp = "0x" + abi_encode(
        ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"],
        [10**30, 0, 0, 0, 0, 0, True],
    ).hex()
    liq_resp = "0x" + abi_encode(["uint128"], [10**18]).hex()
    fee_resp_500 = "0x" + abi_encode(["uint24"], [500]).hex()
    fee_resp_3000 = "0x" + abi_encode(["uint24"], [3000]).hex()

    # Only stub a couple of candidates worth — most will fall through and
    # be filtered. We need enough factory responses for top_pools_by_tvl
    # to iterate. Default candidate set has 11 pairs; we stub the first
    # two as "found" and the rest will fail to fetch (no stub).
    factory_resps = [pool_resp, pool_resp]
    pool_resps_per_pair = [slot0_resp, liq_resp, fee_resp_500,
                           slot0_resp, liq_resp, fee_resp_3000]
    client = StubClient(
        {
            KUMBAYA_FACTORY: factory_resps,
            fake_pool: pool_resps_per_pair,
        }
    )
    proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
    overview = await proto.dex_overview()
    assert isinstance(overview, DexOverview)
    assert overview.venue_count == 1
    venue = overview.venues[0]
    assert isinstance(venue, DexVenueOverview)
    assert venue.venue == "kumbaya"
    assert venue.category == "dex_spot"
    assert venue.pool_count == 2
    assert all(isinstance(p, PoolInfo) for p in venue.top_pools)


@pytest.mark.asyncio
async def test_dex_overview_empty_when_no_dex_spot_in_registry() -> None:
    aave_only = ProtocolEntry(
        key="aave_v3",
        name="Aave V3",
        category="lending",
        priority=1,
        status="active",
        docs_url="",
        addresses={
            "pool": "0x" + "1" * 40,
            "pool_addresses_provider": "0x" + "2" * 40,
            "oracle": "0x" + "3" * 40,
            "ui_pool_data_provider": "0x" + "4" * 40,
            "protocol_data_provider": "0x" + "5" * 40,
        },
        abi_paths={},
    )
    reg = ProtocolRegistry({"aave_v3": aave_only})
    proto = MegaETHProtocols(client=StubClient({}), registry=reg)
    overview = await proto.dex_overview()
    assert overview.venue_count == 0
    assert overview.total_pool_count == 0


def test__kumbaya_helper_rejects_non_dex_venue() -> None:
    """Internal helper guards against passing a lending venue."""
    proto = MegaETHProtocols(client=StubClient({}))
    with pytest.raises(ValueError, match="not a DEX-spot venue"):
        proto._kumbaya("aave_v3")


def test__kumbaya_helper_succeeds_for_dex_spot() -> None:
    proto = MegaETHProtocols(client=StubClient({}))
    kb = proto._kumbaya("kumbaya")
    assert isinstance(kb.addresses, KumbayaAddresses)
    assert kb.addresses.factory == KUMBAYA_FACTORY


def test_dex_routing_table_lists_kumbaya() -> None:
    """The internal routing table builder picks up kumbaya from the registry."""
    proto = MegaETHProtocols(client=StubClient({}), registry=ProtocolRegistry.from_yaml())
    table = proto._dex_routing_table()
    assert len(table) == 1
    venue, _fn = next(iter(table.entries))
    assert venue == "kumbaya"
