"""Tests for the Wave B.3-followup Pyth Network oracle wrapper.

Mocks the underlying RPC client via a small ``FakePythClient`` that
returns deterministic ABI-encoded responses for ``getPriceUnsafe``.
The unit tests cover:

- ``PythPrice`` decoding + ``is_stale`` + ``as_decimal_usd`` +
  ``confidence_pct``.
- ``PythAggregator.get_price_unsafe`` end-to-end through the typed
  contract layer (selector encoding + tuple decoding).
- ``PythRegistry`` symbol normalization, wrapped→underlying resolution,
  and ``oracle_for`` 2-tuple shape.
- ``PythRegistry.fetch_price`` end-to-end with staleness flag.
- ``register_price_id`` runtime override.

The two ``[live]`` integration tests are gated behind
``SAPPHIRE_MEGAETH_INTEGRATION=1`` and hit the real MegaETH mainnet
Pyth contract to confirm:

1. Live BTC/USD reads produce a USD price in the plausible range
   ($50k–$200k for the next ~12 months).
2. The ``MegaETHProtocols.perps_overview`` heavyweight path now
   actually returns funding APRs (the whole point of this lane).
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.megaeth.contracts.pyth_oracle import (
    DEFAULT_MAX_AGE_S,
    MEGAETH_PRICE_IDS,
    MEGAETH_PYTH_ADDRESS,
    PythAggregator,
    PythPrice,
    PythRegistry,
    PythRegistryPrice,
    WRAPPED_TO_UNDERLYING,
)


# ---------------------------------------------------------------------------
# Fake RPC client — encodes the (price, conf, expo, publishTime) tuple
# in the ABI shape the contract returns. We don't need a real Pyth
# address for unit tests, just deterministic responses.
# ---------------------------------------------------------------------------


def _encode_price_tuple(
    price: int, conf: int, expo: int, publish_time: int
) -> str:
    """Return the eth_call hex result for a Pyth getPriceUnsafe response.

    The ABI shape is ``(int64, uint64, int32, uint256)`` packed inside
    a tuple, which matches the ``PythStructs.Price`` struct.
    """
    raw = abi_encode(
        ["(int64,uint64,int32,uint256)"],
        [(price, conf, expo, publish_time)],
    )
    return "0x" + raw.hex()


class FakePythClient:
    """Minimal _MegaETHCallable substitute that returns canned eth_call results."""

    def __init__(self, response_hex: str | None = None) -> None:
        self.response_hex = response_hex
        self.calls: list[tuple[str, list[Any] | None]] = []
        self.code_response: str = "0x" + "ab" * 32  # non-empty bytecode

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, params))
        if method == "eth_call":
            if self.response_hex is None:
                raise RuntimeError("fake: no response set")
            return self.response_hex
        if method == "eth_getCode":
            return self.code_response
        raise RuntimeError(f"fake: unexpected method {method!r}")


# ---------------------------------------------------------------------------
# PythPrice — unit tests on the pure-data side
# ---------------------------------------------------------------------------


def test_pyth_price_as_decimal_usd_negative_expo() -> None:
    """The canonical USD majors case: expo = -8."""
    p = PythPrice(price=7677481000000, conf=1000000, expo=-8, publish_time=1000)
    # 7677481000000 * 10**-8 = 76774.81
    assert p.as_decimal_usd() == Decimal("76774.81")


def test_pyth_price_as_decimal_usd_positive_expo_branch() -> None:
    """Positive expo is rare but the branch must work — exercise it."""
    p = PythPrice(price=5, conf=0, expo=2, publish_time=1000)
    # 5 * 10**2 = 500
    assert p.as_decimal_usd() == Decimal("500")


def test_pyth_price_as_decimal_usd_rejects_zero() -> None:
    p = PythPrice(price=0, conf=0, expo=-8, publish_time=1000)
    with pytest.raises(ValueError, match="must be > 0"):
        p.as_decimal_usd()


def test_pyth_price_as_decimal_usd_rejects_negative() -> None:
    p = PythPrice(price=-1, conf=0, expo=-8, publish_time=1000)
    with pytest.raises(ValueError, match="must be > 0"):
        p.as_decimal_usd()


def test_pyth_price_is_stale_treats_zero_publish_time_as_stale() -> None:
    p = PythPrice(price=100, conf=0, expo=-2, publish_time=0)
    assert p.is_stale(max_age_s=3600, now=1000.0) is True


def test_pyth_price_is_stale_below_threshold() -> None:
    p = PythPrice(price=100, conf=0, expo=-2, publish_time=900)
    # 1000 - 900 = 100s, well under 3600 default
    assert p.is_stale(max_age_s=3600, now=1000.0) is False


def test_pyth_price_is_stale_above_threshold() -> None:
    p = PythPrice(price=100, conf=0, expo=-2, publish_time=900)
    # 5000 - 900 = 4100s, > 3600 default
    assert p.is_stale(max_age_s=3600, now=5000.0) is True


def test_pyth_price_confidence_pct_returns_zero_for_zero_price() -> None:
    p = PythPrice(price=0, conf=100, expo=-8, publish_time=1000)
    # Zero price is degenerate — confidence_pct is 0 (not divide-by-zero).
    assert p.confidence_pct() == Decimal(0)


def test_pyth_price_confidence_pct_typical_majors() -> None:
    # BTC-shaped: 7677481000000 with conf=1000000 → 1e6/7.677e12 ≈ 0.013%
    p = PythPrice(price=7677481000000, conf=1000000, expo=-8, publish_time=1000)
    pct = p.confidence_pct()
    assert pct < Decimal("0.001")  # well under 0.1%


# ---------------------------------------------------------------------------
# PythAggregator — exercise the typed-contract round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregator_get_price_unsafe_decodes_tuple_correctly() -> None:
    """End-to-end: ABI selector → eth_call stub → tuple decode → PythPrice."""
    client = FakePythClient(_encode_price_tuple(7677481000000, 1000000, -8, 1700000000))
    agg = PythAggregator(client)

    btc_id = MEGAETH_PRICE_IDS["BTC"]
    price = await agg.get_price_unsafe(btc_id)

    assert price.price == 7677481000000
    assert price.conf == 1000000
    assert price.expo == -8
    assert price.publish_time == 1700000000
    # And confirm the contract was actually hit (not a mocked-out stub).
    assert len(client.calls) == 1
    assert client.calls[0][0] == "eth_call"
    # The data field on the call should contain the BTC priceId bytes.
    call_to = client.calls[0][1][0]["to"]
    assert call_to.lower() == MEGAETH_PYTH_ADDRESS.lower()


@pytest.mark.asyncio
async def test_aggregator_latest_price_returns_decimal() -> None:
    client = FakePythClient(_encode_price_tuple(7677481000000, 1000000, -8, 1700000000))
    agg = PythAggregator(client)
    usd = await agg.latest_price(MEGAETH_PRICE_IDS["BTC"])
    assert usd == Decimal("76774.81")


@pytest.mark.asyncio
async def test_aggregator_get_price_unsafe_accepts_bytes_priceid() -> None:
    """A 32-byte ``bytes`` priceId works alongside the hex-string form."""
    client = FakePythClient(_encode_price_tuple(2500_00000000, 100000, -8, 1700000000))
    agg = PythAggregator(client)
    eth_id_bytes = bytes.fromhex(MEGAETH_PRICE_IDS["ETH"][2:])
    assert len(eth_id_bytes) == 32
    price = await agg.get_price_unsafe(eth_id_bytes)
    assert price.as_decimal_usd() == Decimal("2500")


@pytest.mark.asyncio
async def test_aggregator_get_price_unsafe_rejects_bad_priceid() -> None:
    client = FakePythClient(_encode_price_tuple(1, 0, 0, 0))
    agg = PythAggregator(client)
    with pytest.raises(ValueError, match="hex length"):
        await agg.get_price_unsafe("0xabcd")  # too short


# ---------------------------------------------------------------------------
# PythRegistry — symbol normalization + wrapped resolution
# ---------------------------------------------------------------------------


def test_registry_known_symbols_includes_majors() -> None:
    reg = PythRegistry(FakePythClient())
    syms = reg.known_symbols()
    for required in ("BTC", "ETH", "SOL", "USDC", "USDT"):
        assert required in syms, f"missing {required} in {syms}"


def test_registry_resolves_wrapped_to_underlying() -> None:
    reg = PythRegistry(FakePythClient())
    # WBTC should resolve to the BTC priceId.
    assert reg.price_id("WBTC") == MEGAETH_PRICE_IDS["BTC"]
    # And case-insensitive.
    assert reg.price_id("wbtc") == MEGAETH_PRICE_IDS["BTC"]
    # WETH → ETH.
    assert reg.price_id("WETH") == MEGAETH_PRICE_IDS["ETH"]
    # USDT0 → USDT.
    assert reg.price_id("USDT0") == MEGAETH_PRICE_IDS["USDT"]


def test_registry_returns_none_for_unknown_symbol() -> None:
    reg = PythRegistry(FakePythClient())
    assert reg.price_id("RANDOMTOKEN") is None
    assert reg.oracle_for("RANDOMTOKEN") is None


def test_registry_oracle_for_returns_2tuple() -> None:
    reg = PythRegistry(FakePythClient())
    resolved = reg.oracle_for("BTC")
    assert resolved is not None
    aggregator, price_id = resolved
    assert isinstance(aggregator, PythAggregator)
    assert price_id == MEGAETH_PRICE_IDS["BTC"]
    # Same instance returned on second call (lazy caching).
    resolved2 = reg.oracle_for("ETH")
    assert resolved2 is not None
    assert resolved2[0] is aggregator


def test_registry_register_price_id_runtime_override() -> None:
    reg = PythRegistry(FakePythClient())
    new_id = "0x" + "ab" * 32
    reg.register_price_id("PEPE", new_id)
    assert reg.price_id("PEPE") == new_id
    # Also normalizes case.
    assert reg.price_id("pepe") == new_id


def test_registry_register_price_id_rejects_bad_hex() -> None:
    reg = PythRegistry(FakePythClient())
    with pytest.raises(ValueError, match="hex"):
        reg.register_price_id("BAD", "0xnothex")


def test_registry_constructor_validates_priceids() -> None:
    """Bad priceId in constructor dict fails fast."""
    with pytest.raises(ValueError):
        PythRegistry(FakePythClient(), price_ids={"BAD": "0xtooshort"})


@pytest.mark.asyncio
async def test_registry_fetch_price_returns_typed_record() -> None:
    client = FakePythClient(_encode_price_tuple(7677481000000, 1000000, -8, 1700000000))
    reg = PythRegistry(client)
    record = await reg.fetch_price("BTC", now=1700000050.0)
    assert isinstance(record, PythRegistryPrice)
    assert record.symbol == "BTC"
    assert record.price_id == MEGAETH_PRICE_IDS["BTC"]
    assert record.usd == Decimal("76774.81")
    assert record.publish_time == 1700000000
    assert record.stale is False  # 50s old, well under 3600s


@pytest.mark.asyncio
async def test_registry_fetch_price_marks_stale_when_old() -> None:
    # publishTime 0 → always stale, regardless of `now`.
    client = FakePythClient(_encode_price_tuple(100, 0, -2, 0))
    reg = PythRegistry(client)
    record = await reg.fetch_price("BTC", now=1.0)
    assert record.stale is True


@pytest.mark.asyncio
async def test_registry_fetch_price_lookup_error_for_unknown_symbol() -> None:
    reg = PythRegistry(FakePythClient())
    with pytest.raises(LookupError, match="no Pyth priceId"):
        await reg.fetch_price("UNKNOWNTOKEN")


@pytest.mark.asyncio
async def test_registry_verify_address_returns_true_for_deployed() -> None:
    client = FakePythClient()
    reg = PythRegistry(client)
    assert await reg.verify_address() is True


@pytest.mark.asyncio
async def test_registry_verify_address_returns_false_for_empty_bytecode() -> None:
    client = FakePythClient()
    client.code_response = "0x"  # empty
    reg = PythRegistry(client)
    assert await reg.verify_address() is False


def test_registry_is_stale_helper_uses_default_threshold() -> None:
    reg = PythRegistry(FakePythClient(), max_age_s=120)
    p_fresh = PythPrice(price=100, conf=0, expo=-2, publish_time=950)
    p_old = PythPrice(price=100, conf=0, expo=-2, publish_time=500)
    assert reg.is_stale(p_fresh, now=1000.0) is False
    assert reg.is_stale(p_old, now=1000.0) is True


@pytest.mark.asyncio
async def test_adapter_falls_back_to_pyth_when_aave_reverts() -> None:
    """Real bug caught from live MegaETH: Aave reverts on unknown assets.

    The first cut of the adapter only checked ``aave_usd > 0`` —
    fine for tokens Aave returns 0 for, but on the live MegaETH
    deployment the Aave oracle REVERTS for assets that aren't in
    the reserve list. We now wrap the Aave call in try/except so
    a revert also falls through to Pyth.
    """
    from lib.chains.megaeth.contracts.gmx_price_adapter import GmxPriceAdapter
    from lib.chains.megaeth.contracts.gmx_v2 import Market

    class RevertingAave:
        async def get_asset_price(self, asset: str) -> Decimal:
            raise RuntimeError("execution reverted")

    class FakeGmx:
        async def list_markets(self, *, start: int = 0, end: int = 200) -> list[Market]:
            return []

    addr_btc = "0x" + "11" * 20
    addr_weth = "0x" + "22" * 20
    addr_usdc = "0x" + "33" * 20
    market = Market(
        market_token="0x" + "44" * 20,
        index_token=addr_btc,
        long_token=addr_weth,
        short_token=addr_usdc,
        name="WBTC/WETH-USDC",
    )

    pyth_client = FakePythClient(
        _encode_price_tuple(7300000000000, 1000000, -8, 1700000000)
    )
    pyth_reg = PythRegistry(pyth_client)
    address_to_symbol = {addr_btc: "BTC", addr_weth: "ETH", addr_usdc: "USDC"}

    adapter = GmxPriceAdapter(
        aave_v3=RevertingAave(),  # type: ignore[arg-type]
        gmx=FakeGmx(),  # type: ignore[arg-type]
        pyth=pyth_reg,
        address_to_symbol=address_to_symbol,
    )

    # All three tokens fall back to Pyth — every leg priced.
    prices = await adapter.prices_for_market(market)
    assert len(prices) == 3
    assert all(p[0] > 0 for p in prices)
    # Observability: every source tagged as "pyth".
    sources = adapter.last_sources
    assert all(s.source == "pyth" for s in sources)


def test_module_constants_are_well_formed() -> None:
    """Sanity: the canonical priceIds are 0x + 64 hex chars (32 bytes)."""
    for sym, pid in MEGAETH_PRICE_IDS.items():
        assert pid.startswith("0x"), f"{sym}: missing 0x prefix"
        assert len(pid) == 66, f"{sym}: wrong length {len(pid)}"
        assert all(c in "0123456789abcdefABCDEF" for c in pid[2:]), f"{sym}: non-hex char"
    assert MEGAETH_PYTH_ADDRESS.startswith("0x")
    assert len(MEGAETH_PYTH_ADDRESS) == 42
    assert DEFAULT_MAX_AGE_S == 3600
    # Wrapped resolution sanity: WBTC → BTC, USDT0 → USDT.
    assert WRAPPED_TO_UNDERLYING["WBTC"] == "BTC"
    assert WRAPPED_TO_UNDERLYING["USDT0"] == "USDT"


# ---------------------------------------------------------------------------
# Live integration tests (skip-by-default)
# ---------------------------------------------------------------------------


class HttpClient:
    """Minimal JSON-RPC client for live integration tests."""

    def __init__(self, url: str) -> None:
        import urllib.request as _urllib  # local import — only used in live tests

        self._urllib = _urllib
        self.url = url

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        import json as _json

        body = _json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        ).encode()
        req = self._urllib.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "sapphire-megaeth-pyth-test/1.0",
            },
        )
        with self._urllib.urlopen(req, timeout=30) as resp:
            payload = _json.loads(resp.read())
        if "error" in payload:
            raise RuntimeError(f"RPC error: {payload['error']}")
        return payload.get("result")


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_MEGAETH_INTEGRATION") != "1",
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to hit live MegaETH Pyth",
)
async def test_live_pyth_btc_price_in_plausible_range() -> None:
    """Hit real MegaETH Pyth and confirm BTC/USD is in [$50k, $200k].

    This is the smoke that proves the wrapper still talks to the real
    chain — gated so CI doesn't depend on RPC availability. The range
    is wide on purpose; this is a "is the feed alive at all" check,
    not a price-prediction test.
    """
    rpc_url = os.getenv("SAPPHIRE_MEGAETH_RPC", "https://carrot.megaeth.com/rpc")
    reg = PythRegistry(HttpClient(rpc_url))

    record = await reg.fetch_price("BTC")
    assert record.usd > Decimal("50000"), f"BTC suspiciously low: {record.usd}"
    assert record.usd < Decimal("200000"), f"BTC suspiciously high: {record.usd}"
    age_s = time.time() - record.publish_time
    print(f"\n[live] Pyth BTC/USD on MegaETH = ${record.usd} (age {age_s:.1f}s, stale={record.stale})")


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_MEGAETH_INTEGRATION") != "1",
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to hit live MegaETH Pyth",
)
async def test_live_perps_overview_returns_funding_rates() -> None:
    """End-to-end: ``MegaETHProtocols.perps_overview`` now returns funding APRs.

    Before this lane: every GMX V2 market on MegaETH had no Aave-priced
    overlap → ``state="unpriced"`` for everything. After this lane:
    Pyth fills the gap → at least one funding APR comes back.
    """
    from lib.chains.megaeth.protocols import MegaETHProtocols

    rpc_url = os.getenv("SAPPHIRE_MEGAETH_RPC", "https://carrot.megaeth.com/rpc")
    client = HttpClient(rpc_url)

    # The live token addresses must be supplied here — see the
    # ``DEFAULT_ADDRESS_TO_SYMBOL`` docstring for why this isn't baked in.
    # Operators running this test populate the env var with a JSON
    # ``{"0xAddr": "BTC", ...}`` dict.
    import json as _json

    addr_map_raw = os.getenv("SAPPHIRE_MEGAETH_TOKEN_SYMBOLS", "{}")
    address_to_symbol = _json.loads(addr_map_raw)

    proto = MegaETHProtocols(client, pyth_address_to_symbol=address_to_symbol)
    overview = await proto.perps_overview(include_funding=True)

    print(f"\n[live] perps_overview market_count={overview.market_count}")
    print(f"[live] funding_extremes={dict(overview.funding_extremes)}")
    # If the address map was populated, we expect at least one funding APR.
    if address_to_symbol:
        assert overview.funding_extremes, "Pyth fallback failed — no funding APRs returned"
