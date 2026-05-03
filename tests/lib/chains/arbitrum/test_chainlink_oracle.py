"""Unit tests for the Chainlink oracle wrapper + Arbitrum feed registry.

Stubs the chain ``_call`` shape so the wrapper is exercised end-to-end
without touching RPC. The gated integration tests (marked with
``@pytest.mark.integration``) are the ones that actually hit Arbitrum
One via JSON-RPC; skip them in CI by default.

The fake-client encoding mirrors the live ``eth_call`` round-trip — it
intercepts the ``eth_call`` method call, decodes the selector +
arguments, and synthesizes the ABI-encoded return payload that the
real contract would emit. That keeps the tests honest about the
encode/decode pipeline (rather than monkeypatching internals).
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.arbitrum.contracts.chainlink_oracle import (
    ARBITRUM_FEEDS,
    DEFAULT_MAX_AGE_S,
    WRAPPED_TO_UNDERLYING,
    ChainlinkAggregator,
    ChainlinkPrice,
    ChainlinkRegistry,
    ChainlinkRound,
)


# ---------- Fake client ------------------------------------------------------


class FakeClient:
    """Stand-in for a chain client implementing ``_call(method, params)``.

    For ``eth_call`` we look at ``params[0]["to"]`` (the target) +
    ``params[0]["data"]`` (the calldata, hex-encoded selector +
    encoded args), match against a per-address response map keyed by
    the function's 4-byte selector hex, and return the ABI-encoded
    payload. ``eth_getCode`` is also supported for ``verify_addresses``.
    """

    # Selector → encoded return shape for AggregatorV3Interface
    DECIMALS_SELECTOR = "0x313ce567"
    DESCRIPTION_SELECTOR = "0x7284e416"
    LATEST_ROUND_DATA_SELECTOR = "0xfeaf968c"

    def __init__(
        self,
        responses: dict[str, dict[str, str]] | None = None,
        code_responses: dict[str, str] | None = None,
    ) -> None:
        # responses: { lowercased_address: { selector_hex: return_hex } }
        self._responses = {k.lower(): v for k, v in (responses or {}).items()}
        # code_responses: { lowercased_address: getCode_return_hex }
        self._code = {k.lower(): v for k, v in (code_responses or {}).items()}
        self.calls: list[tuple[str, Any]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, params))
        if method == "eth_getCode":
            address = (params or ["0x", "latest"])[0]
            return self._code.get(address.lower(), "0x")
        if method != "eth_call":
            raise ValueError(f"FakeClient: unhandled method {method!r}")
        call_obj = (params or [{}])[0]
        addr = call_obj.get("to", "").lower()
        data = call_obj.get("data", "")
        # First 10 hex chars = "0x" + 4-byte selector
        selector = data[:10] if isinstance(data, str) else ""
        per_addr = self._responses.get(addr, {})
        if selector not in per_addr:
            raise ValueError(
                f"FakeClient: no response wired for addr={addr} selector={selector}"
            )
        return per_addr[selector]


def _encode_decimals(d: int) -> str:
    return "0x" + abi_encode(["uint8"], [int(d)]).hex()


def _encode_description(text: str) -> str:
    return "0x" + abi_encode(["string"], [text]).hex()


def _encode_latest_round_data(
    *,
    round_id: int,
    answer: int,
    started_at: int,
    updated_at: int,
    answered_in_round: int,
) -> str:
    payload = abi_encode(
        ["uint80", "int256", "uint256", "uint256", "uint80"],
        [round_id, answer, started_at, updated_at, answered_in_round],
    )
    return "0x" + payload.hex()


# ---------- ChainlinkRound + staleness --------------------------------------


def test_chainlink_round_is_stale_when_older_than_threshold() -> None:
    now = 1_800_000_000.0
    fresh = ChainlinkRound(
        round_id=1, answer=100, started_at=int(now - 100), updated_at=int(now - 100),
        answered_in_round=1,
    )
    stale = ChainlinkRound(
        round_id=2, answer=100, started_at=int(now - 7200), updated_at=int(now - 7200),
        answered_in_round=2,
    )
    assert fresh.is_stale(max_age_s=3600, now=now) is False
    assert stale.is_stale(max_age_s=3600, now=now) is True


def test_chainlink_round_treats_zero_updated_at_as_stale() -> None:
    """Some feeds report updated_at=0 on boot — treat as unconditionally stale."""
    rd = ChainlinkRound(round_id=0, answer=100, started_at=0, updated_at=0, answered_in_round=0)
    assert rd.is_stale(max_age_s=3600, now=time.time()) is True


# ---------- ChainlinkAggregator wrapper -------------------------------------


@pytest.mark.asyncio
async def test_aggregator_decimals_returns_int() -> None:
    addr = "0x" + "a" * 40
    client = FakeClient({addr: {FakeClient.DECIMALS_SELECTOR: _encode_decimals(8)}})
    agg = ChainlinkAggregator(client, addr)
    assert await agg.decimals() == 8


@pytest.mark.asyncio
async def test_aggregator_decimals_caches_after_first_read() -> None:
    addr = "0x" + "a" * 40
    client = FakeClient({addr: {FakeClient.DECIMALS_SELECTOR: _encode_decimals(8)}})
    agg = ChainlinkAggregator(client, addr)
    await agg.decimals()
    await agg.decimals()
    # Only one decimals call should have hit the wire.
    decimals_calls = [c for c in client.calls if c[0] == "eth_call"]
    assert len(decimals_calls) == 1


@pytest.mark.asyncio
async def test_aggregator_latest_round_data_decodes_5_tuple() -> None:
    addr = "0x" + "a" * 40
    client = FakeClient(
        {
            addr: {
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=42, answer=7677481000000, started_at=100, updated_at=200,
                    answered_in_round=42,
                ),
            }
        }
    )
    agg = ChainlinkAggregator(client, addr)
    rd = await agg.latest_round_data()
    assert rd.round_id == 42
    assert rd.answer == 7677481000000  # BTC at $76,774.81 with 8 decimals
    assert rd.started_at == 100
    assert rd.updated_at == 200
    assert rd.answered_in_round == 42


@pytest.mark.asyncio
async def test_aggregator_latest_price_applies_decimals_scaling() -> None:
    addr = "0x" + "a" * 40
    client = FakeClient(
        {
            addr: {
                FakeClient.DECIMALS_SELECTOR: _encode_decimals(8),
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=7677481000000, started_at=100, updated_at=200,
                    answered_in_round=1,
                ),
            }
        }
    )
    agg = ChainlinkAggregator(client, addr)
    price = await agg.latest_price()
    # 7,677,481,000,000 / 1e8 == 76774.81
    assert price == Decimal("76774.81")


@pytest.mark.asyncio
async def test_aggregator_latest_price_raises_on_non_positive_answer() -> None:
    addr = "0x" + "a" * 40
    client = FakeClient(
        {
            addr: {
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=0, started_at=100, updated_at=200,
                    answered_in_round=1,
                ),
            }
        }
    )
    agg = ChainlinkAggregator(client, addr)
    with pytest.raises(ValueError, match="non-positive"):
        await agg.latest_price()


@pytest.mark.asyncio
async def test_aggregator_description_decodes_string() -> None:
    addr = "0x" + "a" * 40
    client = FakeClient(
        {addr: {FakeClient.DESCRIPTION_SELECTOR: _encode_description("BTC / USD")}}
    )
    agg = ChainlinkAggregator(client, addr)
    assert await agg.description() == "BTC / USD"


# ---------- ChainlinkRegistry ------------------------------------------------


def test_registry_known_symbols_includes_all_majors() -> None:
    reg = ChainlinkRegistry(client=FakeClient())
    known = reg.known_symbols()
    for sym in ("BTC", "ETH", "SOL", "AVAX", "DOGE", "LINK"):
        assert sym in known


def test_registry_resolves_wrapped_token_to_underlying() -> None:
    reg = ChainlinkRegistry(client=FakeClient())
    # WBTC should resolve to the BTC feed (via WRAPPED_TO_UNDERLYING).
    assert reg.feed_address("WBTC") == ARBITRUM_FEEDS["BTC"]
    assert reg.feed_address("weth") == ARBITRUM_FEEDS["ETH"]


def test_registry_unknown_symbol_returns_none() -> None:
    reg = ChainlinkRegistry(client=FakeClient())
    assert reg.feed_address("DOESNOTEXIST") is None
    assert reg.oracle_for("DOESNOTEXIST") is None


def test_registry_register_feed_overrides_address() -> None:
    reg = ChainlinkRegistry(client=FakeClient())
    new_addr = "0x" + "9" * 40
    reg.register_feed("BTC", new_addr)
    assert reg.feed_address("BTC") == new_addr


def test_registry_register_feed_rejects_invalid_address() -> None:
    reg = ChainlinkRegistry(client=FakeClient())
    with pytest.raises(ValueError, match="invalid feed address"):
        reg.register_feed("BTC", "nope")


def test_registry_oracle_for_caches_instance() -> None:
    reg = ChainlinkRegistry(client=FakeClient())
    a1 = reg.oracle_for("BTC")
    a2 = reg.oracle_for("BTC")
    # Same instance — caching avoids re-creating the wrapper for every call.
    assert a1 is a2


@pytest.mark.asyncio
async def test_registry_fetch_price_returns_typed_chainlink_price() -> None:
    btc_addr = ARBITRUM_FEEDS["BTC"].lower()
    now = 1_800_000_000.0
    client = FakeClient(
        {
            btc_addr: {
                FakeClient.DECIMALS_SELECTOR: _encode_decimals(8),
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=7677481000000,
                    started_at=int(now - 60), updated_at=int(now - 60),
                    answered_in_round=1,
                ),
            }
        }
    )
    reg = ChainlinkRegistry(client=client)
    cp = await reg.fetch_price("BTC", now=now)
    assert isinstance(cp, ChainlinkPrice)
    assert cp.symbol == "BTC"
    assert cp.feed_address.lower() == btc_addr
    assert cp.usd == Decimal("76774.81")
    assert cp.stale is False


@pytest.mark.asyncio
async def test_registry_fetch_price_flags_stale_feed() -> None:
    btc_addr = ARBITRUM_FEEDS["BTC"].lower()
    now = 1_800_000_000.0
    client = FakeClient(
        {
            btc_addr: {
                FakeClient.DECIMALS_SELECTOR: _encode_decimals(8),
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=7000000000000,
                    started_at=int(now - 7200),  # 2 hours ago — stale
                    updated_at=int(now - 7200),
                    answered_in_round=1,
                ),
            }
        }
    )
    reg = ChainlinkRegistry(client=client, max_age_s=3600)
    cp = await reg.fetch_price("BTC", now=now)
    assert cp.stale is True
    assert cp.usd == Decimal("70000")  # still surfaces the price


@pytest.mark.asyncio
async def test_registry_fetch_price_unknown_symbol_raises_lookup_error() -> None:
    reg = ChainlinkRegistry(client=FakeClient())
    with pytest.raises(LookupError, match="no Chainlink feed"):
        await reg.fetch_price("DOESNOTEXIST")


# ---------- GMX adapter Chainlink fallback path ------------------------------


@pytest.mark.asyncio
async def test_gmx_adapter_falls_back_to_chainlink_when_aave_returns_zero() -> None:
    """The headline integration: WBTC unpriced by Aave should now price via Chainlink."""
    from lib.chains.arbitrum.contracts.gmx_price_adapter import GmxPriceAdapter

    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"  # WBTC on Arbitrum
    btc_feed = ARBITRUM_FEEDS["BTC"].lower()
    now = 1_800_000_000.0

    class _AaveZero:
        async def get_asset_price(self, asset: str) -> Decimal:
            return Decimal(0)

    client = FakeClient(
        {
            btc_feed: {
                FakeClient.DECIMALS_SELECTOR: _encode_decimals(8),
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=7677481000000,
                    started_at=int(now - 60), updated_at=int(now - 60),
                    answered_in_round=1,
                ),
            }
        }
    )
    reg = ChainlinkRegistry(client=client)
    adapter = GmxPriceAdapter(_AaveZero(), chainlink=reg)
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "chainlink"
    assert p.stale is False
    assert p.usd == Decimal("76774.81")


@pytest.mark.asyncio
async def test_gmx_adapter_falls_back_to_chainlink_when_aave_reverts() -> None:
    """Aave hard-revert path also delegates to Chainlink."""
    from lib.chains.arbitrum.contracts.gmx_price_adapter import GmxPriceAdapter

    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    btc_feed = ARBITRUM_FEEDS["BTC"].lower()
    now = 1_800_000_000.0

    class _AaveRevert:
        async def get_asset_price(self, asset: str) -> Decimal:
            raise RuntimeError("execution reverted")

    client = FakeClient(
        {
            btc_feed: {
                FakeClient.DECIMALS_SELECTOR: _encode_decimals(8),
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=7000000000000,
                    started_at=int(now - 60), updated_at=int(now - 60),
                    answered_in_round=1,
                ),
            }
        }
    )
    reg = ChainlinkRegistry(client=client)
    adapter = GmxPriceAdapter(_AaveRevert(), chainlink=reg)
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "chainlink"
    assert p.usd == Decimal("70000")


@pytest.mark.asyncio
async def test_gmx_adapter_propagates_stale_flag_from_chainlink() -> None:
    """The stale flag from Chainlink must propagate to the TokenPrice.

    We use updated_at=1 (effectively the unix epoch) so the staleness
    check fires regardless of the actual wall-clock time at test run.
    """
    from lib.chains.arbitrum.contracts.gmx_price_adapter import GmxPriceAdapter

    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    btc_feed = ARBITRUM_FEEDS["BTC"].lower()

    class _AaveZero:
        async def get_asset_price(self, asset: str) -> Decimal:
            return Decimal(0)

    client = FakeClient(
        {
            btc_feed: {
                FakeClient.DECIMALS_SELECTOR: _encode_decimals(8),
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=7000000000000,
                    started_at=1,
                    updated_at=1,  # 1970 → unconditionally stale at runtime
                    answered_in_round=1,
                ),
            }
        }
    )
    reg = ChainlinkRegistry(client=client, max_age_s=3600)
    adapter = GmxPriceAdapter(_AaveZero(), chainlink=reg)
    p = await adapter.fetch_token_price(wbtc)
    # Stale propagation only works if the registry computes stale at
    # fetch time; the adapter forwards the flag verbatim.
    assert p.source == "chainlink"
    assert p.stale is True


@pytest.mark.asyncio
async def test_gmx_adapter_raises_unavailable_when_both_oracles_fail() -> None:
    """No Chainlink registry + Aave returns 0 still raises (back-compat)."""
    from lib.chains.arbitrum.contracts.gmx_price_adapter import (
        GmxPriceAdapter,
        PriceUnavailable,
    )

    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"

    class _AaveZero:
        async def get_asset_price(self, asset: str) -> Decimal:
            return Decimal(0)

    adapter = GmxPriceAdapter(_AaveZero())  # no chainlink
    with pytest.raises(PriceUnavailable, match="non-positive"):
        await adapter.fetch_token_price(wbtc)


@pytest.mark.asyncio
async def test_gmx_adapter_uses_aave_when_aave_priced_even_with_chainlink_present() -> None:
    """Aave is the primary; Chainlink only fires on Aave failure."""
    from lib.chains.arbitrum.contracts.gmx_price_adapter import GmxPriceAdapter

    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    btc_feed = ARBITRUM_FEEDS["BTC"].lower()

    class _AavePriced:
        async def get_asset_price(self, asset: str) -> Decimal:
            # Different price than Chainlink would return — proves we
            # used the Aave path.
            return Decimal("80000")

    client = FakeClient(
        {
            btc_feed: {
                FakeClient.DECIMALS_SELECTOR: _encode_decimals(8),
                FakeClient.LATEST_ROUND_DATA_SELECTOR: _encode_latest_round_data(
                    round_id=1, answer=7000000000000, started_at=100, updated_at=200,
                    answered_in_round=1,
                ),
            }
        }
    )
    reg = ChainlinkRegistry(client=client)
    adapter = GmxPriceAdapter(_AavePriced(), chainlink=reg)
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "aave"
    assert p.usd == Decimal("80000")


# ---------- Wrapped → underlying mapping ------------------------------------


def test_wrapped_to_underlying_covers_btc_eth_sol_avax_doge() -> None:
    assert WRAPPED_TO_UNDERLYING["WBTC"] == "BTC"
    assert WRAPPED_TO_UNDERLYING["WETH"] == "ETH"
    assert WRAPPED_TO_UNDERLYING["WSOL"] == "SOL"
    assert WRAPPED_TO_UNDERLYING["WAVAX"] == "AVAX"
    assert WRAPPED_TO_UNDERLYING["WDOGE"] == "DOGE"


# ---------- verify_addresses --------------------------------------------------


@pytest.mark.asyncio
async def test_verify_addresses_distinguishes_deployed_from_empty() -> None:
    reg = ChainlinkRegistry(
        client=FakeClient(
            code_responses={
                ARBITRUM_FEEDS["BTC"]: "0x6080604052",  # has bytecode
                ARBITRUM_FEEDS["ETH"]: "0x",  # empty
            },
        ),
    )
    out = await reg.verify_addresses()
    # Only addresses with non-empty bytecode are True.
    assert out["BTC"] is True
    assert out["ETH"] is False
    # SOL/AVAX/DOGE/LINK aren't in the code_responses map → empty → False.
    for sym in ("SOL", "AVAX", "DOGE", "LINK"):
        assert out[sym] is False


# ---------- Gated integration tests ------------------------------------------
# These hit live Arbitrum One via JSON-RPC. Skipped unless
# SAPPHIRE_RUN_INTEGRATION=1 (and an RPC URL is set).


def _run_integration() -> bool:
    return os.getenv("SAPPHIRE_RUN_INTEGRATION", "0") == "1"


def _arbitrum_rpc_url() -> str:
    return os.getenv("SAPPHIRE_ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not _run_integration(), reason="set SAPPHIRE_RUN_INTEGRATION=1")
async def test_integration_live_btc_usd_price_in_plausible_range() -> None:
    """Live Chainlink BTC/USD on Arbitrum must report a sane USD price."""
    import httpx  # noqa: PLC0415 — late import keeps unit-test path httpx-free

    rpc_url = _arbitrum_rpc_url()

    class _LiveClient:
        async def _call(self, method: str, params: list[Any] | None = None) -> Any:
            with httpx.Client(timeout=10.0) as h:
                r = h.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": method,
                        "params": params or [],
                        "id": 1,
                    },
                )
                r.raise_for_status()
                body = r.json()
                if "error" in body:
                    raise RuntimeError(body["error"])
                return body.get("result")

    reg = ChainlinkRegistry(client=_LiveClient())
    cp = await reg.fetch_price("BTC")
    # Plausible BTC range (50k - 200k USD as of 2026-04-30 era).
    assert Decimal("50000") < cp.usd < Decimal("200000"), (
        f"BTC price out of plausible range: {cp.usd}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not _run_integration(), reason="set SAPPHIRE_RUN_INTEGRATION=1")
async def test_integration_perps_overview_now_prices_btc_market() -> None:
    """The headline behavior change: BTC market should price post-fallback."""
    import httpx  # noqa: PLC0415

    from lib.chains.arbitrum.protocols import ArbitrumProtocols

    rpc_url = _arbitrum_rpc_url()

    class _LiveClient:
        async def _call(self, method: str, params: list[Any] | None = None) -> Any:
            with httpx.Client(timeout=15.0) as h:
                r = h.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": method,
                        "params": params or [],
                        "id": 1,
                    },
                )
                r.raise_for_status()
                body = r.json()
                if "error" in body:
                    raise RuntimeError(body["error"])
                return body.get("result")

    proto = ArbitrumProtocols(client=_LiveClient())
    overview = await proto.perps_overview(max_markets=60)
    assert overview.priced_count > 4, (
        f"Chainlink fallback should bump priced markets above 4 (was Lane I baseline); "
        f"got {overview.priced_count}"
    )
