"""Unit + gated-integration tests for the Arbitrum Pyth oracle wrapper.

Stubs the chain ``_call`` shape so the wrapper is exercised end-to-end
without touching RPC. The gated integration test (marked with
``@pytest.mark.skipif``) is the one that actually hits Arbitrum One via
JSON-RPC; skip it in CI by default by leaving
``SAPPHIRE_RUN_INTEGRATION`` unset.

The fake-client encoding mirrors the live ``eth_call`` round-trip — it
intercepts the ``eth_call`` method call and returns a synthesized
ABI-encoded payload that matches what the real Pyth contract emits.
That keeps the tests honest about the encode/decode pipeline (rather
than monkeypatching internals).
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.arbitrum.contracts.pyth_oracle import (
    ARBITRUM_PRICE_IDS,
    ARBITRUM_PYTH_ADDRESS,
    DEFAULT_MAX_AGE_S,
    WRAPPED_TO_UNDERLYING,
    PythAggregator,
    PythPrice,
    PythRegistry,
    PythRegistryPrice,
)

# ---------------------------------------------------------------------------
# Fake RPC client — encodes the (price, conf, expo, publishTime) tuple
# in the ABI shape the contract returns.
# ---------------------------------------------------------------------------


def _encode_price_tuple(price: int, conf: int, expo: int, publish_time: int) -> str:
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
    """Minimal ``_ChainCallable`` substitute that returns canned eth_call results."""

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
# PythPrice — pure-data side
# ---------------------------------------------------------------------------


def test_pyth_price_as_decimal_usd_negative_expo() -> None:
    """Canonical USD majors: expo = -8."""
    p = PythPrice(price=7677481000000, conf=1000000, expo=-8, publish_time=1000)
    # 7677481000000 * 10**-8 = 76774.81
    assert p.as_decimal_usd() == Decimal("76774.81")


def test_pyth_price_as_decimal_usd_rejects_zero() -> None:
    p = PythPrice(price=0, conf=0, expo=-8, publish_time=1000)
    with pytest.raises(ValueError, match="must be > 0"):
        p.as_decimal_usd()


def test_pyth_price_is_stale_treats_zero_publish_time_as_stale() -> None:
    p = PythPrice(price=100, conf=0, expo=-2, publish_time=0)
    assert p.is_stale(max_age_s=3600, now=1000.0) is True


def test_pyth_price_is_stale_above_threshold() -> None:
    p = PythPrice(price=100, conf=0, expo=-2, publish_time=900)
    # 5000 - 900 = 4100s, > 3600 default
    assert p.is_stale(max_age_s=3600, now=5000.0) is True


def test_pyth_price_is_stale_below_threshold() -> None:
    p = PythPrice(price=100, conf=0, expo=-2, publish_time=900)
    # 1000 - 900 = 100s, well under 3600 default
    assert p.is_stale(max_age_s=3600, now=1000.0) is False


def test_pyth_price_confidence_pct_typical_majors() -> None:
    # BTC-shaped: 7677481000000 with conf=1000000 → 1e6/7.677e12 ≈ 0.013%
    p = PythPrice(price=7677481000000, conf=1000000, expo=-8, publish_time=1000)
    pct = p.confidence_pct()
    assert pct < Decimal("0.001")  # well under 0.1%


# ---------------------------------------------------------------------------
# PythAggregator — typed-contract round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregator_get_price_unsafe_decodes_tuple_correctly() -> None:
    """End-to-end: ABI selector → eth_call stub → tuple decode → PythPrice."""
    client = FakePythClient(_encode_price_tuple(7677481000000, 1000000, -8, 1700000000))
    agg = PythAggregator(client)

    btc_id = ARBITRUM_PRICE_IDS["BTC"]
    price = await agg.get_price_unsafe(btc_id)

    assert price.price == 7677481000000
    assert price.conf == 1000000
    assert price.expo == -8
    assert price.publish_time == 1700000000
    # And confirm the contract was actually hit (not a mocked-out stub).
    assert len(client.calls) == 1
    assert client.calls[0][0] == "eth_call"
    # The 'to' field should be the Arbitrum Pyth contract.
    call_to = client.calls[0][1][0]["to"]
    assert call_to.lower() == ARBITRUM_PYTH_ADDRESS.lower()


@pytest.mark.asyncio
async def test_aggregator_latest_price_returns_decimal() -> None:
    client = FakePythClient(_encode_price_tuple(7677481000000, 1000000, -8, 1700000000))
    agg = PythAggregator(client)
    usd = await agg.latest_price(ARBITRUM_PRICE_IDS["BTC"])
    assert usd == Decimal("76774.81")


@pytest.mark.asyncio
async def test_aggregator_get_price_unsafe_accepts_bytes_priceid() -> None:
    """A 32-byte ``bytes`` priceId works alongside the hex-string form."""
    client = FakePythClient(_encode_price_tuple(2500_00000000, 100000, -8, 1700000000))
    agg = PythAggregator(client)
    eth_id_bytes = bytes.fromhex(ARBITRUM_PRICE_IDS["ETH"][2:])
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


def test_registry_known_symbols_includes_arbitrum_majors() -> None:
    reg = PythRegistry(FakePythClient())
    syms = reg.known_symbols()
    for required in ("BTC", "ETH", "SOL", "AVAX", "DOGE", "LINK", "USDC", "USDT", "ARB"):
        assert required in syms, f"missing {required} in {syms}"


def test_registry_resolves_wrapped_to_underlying() -> None:
    reg = PythRegistry(FakePythClient())
    # WBTC should resolve to the BTC priceId.
    assert reg.price_id("WBTC") == ARBITRUM_PRICE_IDS["BTC"]
    # Case-insensitive.
    assert reg.price_id("wbtc") == ARBITRUM_PRICE_IDS["BTC"]
    assert reg.price_id("WETH") == ARBITRUM_PRICE_IDS["ETH"]
    assert reg.price_id("WAVAX") == ARBITRUM_PRICE_IDS["AVAX"]
    assert reg.price_id("USDT0") == ARBITRUM_PRICE_IDS["USDT"]


def test_registry_unknown_symbol_returns_none() -> None:
    reg = PythRegistry(FakePythClient())
    assert reg.price_id("RANDOMTOKEN") is None
    assert reg.oracle_for("RANDOMTOKEN") is None


def test_registry_oracle_for_returns_2tuple_with_cached_aggregator() -> None:
    reg = PythRegistry(FakePythClient())
    resolved = reg.oracle_for("BTC")
    assert resolved is not None
    aggregator, price_id = resolved
    assert isinstance(aggregator, PythAggregator)
    assert price_id == ARBITRUM_PRICE_IDS["BTC"]
    # Second symbol — should reuse the same aggregator instance (one
    # contract for all feeds).
    resolved2 = reg.oracle_for("ETH")
    assert resolved2 is not None
    assert resolved2[0] is aggregator


def test_registry_register_price_id_runtime_override() -> None:
    reg = PythRegistry(FakePythClient())
    new_id = "0x" + "ab" * 32
    reg.register_price_id("PEPE", new_id)
    assert reg.price_id("PEPE") == new_id
    # Case-normalized.
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
    assert record.price_id == ARBITRUM_PRICE_IDS["BTC"]
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


def test_module_constants_are_well_formed() -> None:
    """Sanity: the canonical priceIds are 0x + 64 hex chars (32 bytes)."""
    for sym, pid in ARBITRUM_PRICE_IDS.items():
        assert pid.startswith("0x"), f"{sym}: missing 0x prefix"
        assert len(pid) == 66, f"{sym}: wrong length {len(pid)}"
        assert all(c in "0123456789abcdefABCDEF" for c in pid[2:]), f"{sym}: non-hex char"
    # Address shape.
    assert ARBITRUM_PYTH_ADDRESS.startswith("0x")
    assert len(ARBITRUM_PYTH_ADDRESS) == 42
    assert DEFAULT_MAX_AGE_S == 3600
    # Wrapped resolution sanity.
    assert WRAPPED_TO_UNDERLYING["WBTC"] == "BTC"
    assert WRAPPED_TO_UNDERLYING["USDT0"] == "USDT"
    # The Arbitrum Pyth address is NOT the MegaETH one — guard against
    # a future cross-chain copy-paste regression.
    assert ARBITRUM_PYTH_ADDRESS.lower() != "0x2880aB155794e7179c9eE2e38200202908C17B43".lower()


# ---------------------------------------------------------------------------
# Live integration test (skip-by-default)
# ---------------------------------------------------------------------------


class _HttpClient:
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
                "User-Agent": "sapphire-arbitrum-pyth-test/1.0",
            },
        )
        with self._urllib.urlopen(req, timeout=30) as resp:
            payload = _json.loads(resp.read())
        if "error" in payload:
            raise RuntimeError(f"RPC error: {payload['error']}")
        return payload.get("result")


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_RUN_INTEGRATION") != "1",
    reason="set SAPPHIRE_RUN_INTEGRATION=1 to hit live Arbitrum Pyth",
)
async def test_live_pyth_btc_price_in_plausible_range() -> None:
    """Hit real Arbitrum Pyth and confirm BTC/USD is in [$50k, $200k].

    This is the smoke that proves the wrapper still talks to the real
    chain — gated so CI doesn't depend on RPC availability. The range
    is wide on purpose; this is a "is the feed alive at all" check,
    not a price-prediction test.
    """
    rpc_url = os.getenv("SAPPHIRE_ARBITRUM_RPC", "https://arb1.arbitrum.io/rpc")
    reg = PythRegistry(_HttpClient(rpc_url))

    # Sanity: Pyth contract bytecode is present.
    assert await reg.verify_address() is True

    record = await reg.fetch_price("BTC")
    assert record.usd > Decimal("50000"), f"BTC suspiciously low: {record.usd}"
    assert record.usd < Decimal("200000"), f"BTC suspiciously high: {record.usd}"
    age_s = time.time() - record.publish_time
    print(
        f"\n[live] Pyth BTC/USD on Arbitrum = ${record.usd} "
        f"(age {age_s:.1f}s, stale={record.stale})"
    )
