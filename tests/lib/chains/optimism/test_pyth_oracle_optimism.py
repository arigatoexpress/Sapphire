"""Tests for the Pyth Network oracle wrapper on Optimism mainnet.

Mirror of ``tests/lib/chains/megaeth/test_pyth_oracle.py`` (PR #603)
adapted to chain id 10. Mocks the underlying RPC client via a small
``FakePythClient`` that returns deterministic ABI-encoded responses
for ``getPriceUnsafe``.

The unit tests cover:

- ``PythPrice`` decoding + ``is_stale`` + ``as_decimal_usd``.
- ``PythAggregator.get_price_unsafe`` end-to-end through the typed
  contract layer (selector encoding + tuple decoding) with the
  Optimism Pyth address.
- ``PythRegistry`` symbol normalization, wrapped→underlying resolution.
- ``OptimismProtocols.pyth_price`` convenience method (soft-fail
  semantics).
- ``classify_optimism`` extension: stale Pyth lifts to WARNING; fresh
  Pyth tagged in telemetry; BLOCK from Aave never overridden.
- ``evaluate_optimism_chain_health`` Aave-revert fallback.

The two ``[live]`` integration tests are gated behind
``SAPPHIRE_OPTIMISM_INTEGRATION=1`` and hit the real Optimism mainnet
Pyth contract:

1. Live BTC/USD reads produce a USD price in the plausible range
   ($50k–$200k for the next ~12 months).
2. Live ``OptimismProtocols.pyth_price("ETH")`` returns a Decimal in
   the plausible range ($1k–$10k).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.optimism.contracts.pyth_oracle import (
    DEFAULT_MAX_AGE_S,
    OPTIMISM_PRICE_IDS,
    OPTIMISM_PYTH_ADDRESS,
    WRAPPED_TO_UNDERLYING,
    PythAggregator,
    PythPrice,
    PythRegistry,
    PythRegistryPrice,
)
from lib.hackathon.optimism_chain_health import (
    PYTH_PROBE_SYMBOLS,
    classify_optimism,
    evaluate_optimism_chain_health,
)

# ---------------------------------------------------------------------------
# Fake RPC client — encodes the (price, conf, expo, publishTime) tuple
# in the ABI shape the contract returns.
# ---------------------------------------------------------------------------


def _encode_price_tuple(
    price: int, conf: int, expo: int, publish_time: int
) -> str:
    """Return the eth_call hex result for a Pyth getPriceUnsafe response."""
    raw = abi_encode(
        ["(int64,uint64,int32,uint256)"],
        [(price, conf, expo, publish_time)],
    )
    return "0x" + raw.hex()


class FakePythClient:
    """Minimal _ChainCallable substitute that returns canned eth_call results."""

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
# Constants pin
# ---------------------------------------------------------------------------


def test_optimism_pyth_address_is_canonical() -> None:
    """Optimism Pyth uses the same CREATE2 address as most other EVMs."""
    assert OPTIMISM_PYTH_ADDRESS == "0xff1a0f4744e8582DF1aE09D5611b887B6a12925C"
    assert OPTIMISM_PYTH_ADDRESS.startswith("0x")
    assert len(OPTIMISM_PYTH_ADDRESS) == 42


def test_module_constants_are_well_formed() -> None:
    """Sanity: the canonical priceIds are 0x + 64 hex chars (32 bytes)."""
    for sym, pid in OPTIMISM_PRICE_IDS.items():
        assert pid.startswith("0x"), f"{sym}: missing 0x prefix"
        assert len(pid) == 66, f"{sym}: wrong length {len(pid)}"
        assert all(c in "0123456789abcdefABCDEF" for c in pid[2:]), f"{sym}: non-hex"
    assert DEFAULT_MAX_AGE_S == 3600
    # Wrapped resolution sanity: WBTC → BTC, USDC.E → USDC.
    assert WRAPPED_TO_UNDERLYING["WBTC"] == "BTC"
    assert WRAPPED_TO_UNDERLYING["USDC.E"] == "USDC"
    assert WRAPPED_TO_UNDERLYING["USDT0"] == "USDT"


def test_optimism_priceids_match_megaeth_for_chain_agnostic_assets() -> None:
    """Pyth priceIds are off-chain feed IDs — same on every chain.

    Locks the cross-chain symmetry so a future bump on one side that
    forgets the other gets caught by CI. Skips cleanly if the MegaETH
    Pyth module hasn't merged yet (PR #603 dependency); the assertion
    activates as soon as both modules coexist on the same branch.
    """
    try:
        from lib.chains.megaeth.contracts.pyth_oracle import (
            MEGAETH_PRICE_IDS,
        )
    except ImportError:
        pytest.skip(
            "lib.chains.megaeth.contracts.pyth_oracle not present "
            "(PR #603 not merged into base); cross-chain symmetry check skipped"
        )
    for sym in ("BTC", "ETH", "SOL", "USDC", "USDT"):
        assert OPTIMISM_PRICE_IDS[sym] == MEGAETH_PRICE_IDS[sym], (
            f"{sym}: priceId differs across chains "
            f"(op={OPTIMISM_PRICE_IDS[sym]!r}, megaeth={MEGAETH_PRICE_IDS[sym]!r})"
        )


# ---------------------------------------------------------------------------
# PythPrice — pure-data side
# ---------------------------------------------------------------------------


def test_pyth_price_as_decimal_usd_negative_expo() -> None:
    """Canonical USD majors case: expo = -8."""
    p = PythPrice(price=7677481000000, conf=1000000, expo=-8, publish_time=1000)
    assert p.as_decimal_usd() == Decimal("76774.81")


def test_pyth_price_is_stale_treats_zero_publish_time_as_stale() -> None:
    p = PythPrice(price=100, conf=0, expo=-2, publish_time=0)
    assert p.is_stale(max_age_s=3600, now=1000.0) is True


def test_pyth_price_is_stale_threshold_boundary() -> None:
    """Below threshold = fresh, above = stale (strict greater-than)."""
    p_fresh = PythPrice(price=100, conf=0, expo=-2, publish_time=900)
    p_stale = PythPrice(price=100, conf=0, expo=-2, publish_time=900)
    # 1000-900 = 100 < 3600 => fresh
    assert p_fresh.is_stale(max_age_s=3600, now=1000.0) is False
    # 5000-900 = 4100 > 3600 => stale
    assert p_stale.is_stale(max_age_s=3600, now=5000.0) is True


def test_pyth_price_as_decimal_usd_rejects_zero() -> None:
    p = PythPrice(price=0, conf=0, expo=-8, publish_time=1000)
    with pytest.raises(ValueError, match="must be > 0"):
        p.as_decimal_usd()


# ---------------------------------------------------------------------------
# PythAggregator — typed-contract round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregator_get_price_unsafe_decodes_tuple_correctly() -> None:
    """End-to-end: ABI selector → eth_call stub → tuple decode → PythPrice.

    Confirms the selector lands on the right address and the decoded
    fields match a realistic BTC reading.
    """
    client = FakePythClient(_encode_price_tuple(7677481000000, 1000000, -8, 1700000000))
    agg = PythAggregator(client)

    btc_id = OPTIMISM_PRICE_IDS["BTC"]
    price = await agg.get_price_unsafe(btc_id)

    assert price.price == 7677481000000
    assert price.conf == 1000000
    assert price.expo == -8
    assert price.publish_time == 1700000000
    assert len(client.calls) == 1
    assert client.calls[0][0] == "eth_call"
    call_to = client.calls[0][1][0]["to"]
    # The aggregator binds to the canonical Optimism Pyth address.
    assert call_to.lower() == OPTIMISM_PYTH_ADDRESS.lower()


@pytest.mark.asyncio
async def test_aggregator_get_price_unsafe_rejects_bad_priceid() -> None:
    client = FakePythClient(_encode_price_tuple(1, 0, 0, 0))
    agg = PythAggregator(client)
    with pytest.raises(ValueError, match="hex length"):
        await agg.get_price_unsafe("0xabcd")


# ---------------------------------------------------------------------------
# PythRegistry — symbol normalization + fetch_price
# ---------------------------------------------------------------------------


def test_registry_resolves_wrapped_to_underlying() -> None:
    reg = PythRegistry(FakePythClient())
    assert reg.price_id("WBTC") == OPTIMISM_PRICE_IDS["BTC"]
    assert reg.price_id("wbtc") == OPTIMISM_PRICE_IDS["BTC"]
    assert reg.price_id("WETH") == OPTIMISM_PRICE_IDS["ETH"]
    assert reg.price_id("USDC.E") == OPTIMISM_PRICE_IDS["USDC"]


def test_registry_returns_none_for_unknown_symbol() -> None:
    reg = PythRegistry(FakePythClient())
    assert reg.price_id("RANDOMTOKEN") is None
    assert reg.oracle_for("RANDOMTOKEN") is None


@pytest.mark.asyncio
async def test_registry_fetch_price_returns_typed_record_fresh() -> None:
    client = FakePythClient(_encode_price_tuple(7677481000000, 1000000, -8, 1700000000))
    reg = PythRegistry(client)
    record = await reg.fetch_price("BTC", now=1700000050.0)
    assert isinstance(record, PythRegistryPrice)
    assert record.symbol == "BTC"
    assert record.price_id == OPTIMISM_PRICE_IDS["BTC"]
    assert record.usd == Decimal("76774.81")
    assert record.publish_time == 1700000000
    assert record.stale is False  # 50s old, well under 3600s


@pytest.mark.asyncio
async def test_registry_fetch_price_marks_stale_when_old() -> None:
    client = FakePythClient(_encode_price_tuple(100, 0, -2, 0))
    reg = PythRegistry(client)
    record = await reg.fetch_price("BTC", now=1.0)
    assert record.stale is True


# ---------------------------------------------------------------------------
# OptimismProtocols facade integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimism_protocols_has_pyth_registry_by_default() -> None:
    """OptimismProtocols(client) constructs a PythRegistry without extra wiring."""
    from lib.chains.optimism.protocols import OptimismProtocols

    proto = OptimismProtocols(FakePythClient())
    assert isinstance(proto.pyth, PythRegistry)
    # Default registry covers the major-feed symbols.
    for sym in ("BTC", "ETH", "USDC"):
        assert proto.pyth.price_id(sym) is not None


@pytest.mark.asyncio
async def test_optimism_protocols_pyth_price_returns_decimal_for_known() -> None:
    from lib.chains.optimism.protocols import OptimismProtocols

    client = FakePythClient(_encode_price_tuple(2500_00000000, 100000, -8, 1700000000))
    proto = OptimismProtocols(client)
    usd = await proto.pyth_price("ETH")
    assert usd == Decimal("2500")


@pytest.mark.asyncio
async def test_optimism_protocols_pyth_price_soft_fails_on_unknown() -> None:
    """Soft-fail: unknown symbol → None, no exception, no RPC call."""
    from lib.chains.optimism.protocols import OptimismProtocols

    client = FakePythClient()
    proto = OptimismProtocols(client)
    result = await proto.pyth_price("ZZZUNKNOWN")
    assert result is None
    # No eth_call should have been issued.
    assert all(c[0] != "eth_call" for c in client.calls)


@pytest.mark.asyncio
async def test_optimism_protocols_pyth_price_soft_fails_on_rpc_error() -> None:
    """Soft-fail: RPC failure → None, not an exception bubble."""
    from lib.chains.optimism.protocols import OptimismProtocols

    class BrokenClient(FakePythClient):
        async def _call(self, method: str, params: list[Any] | None = None) -> Any:
            if method == "eth_call":
                raise RuntimeError("execution reverted")
            return "0xff"

    proto = OptimismProtocols(BrokenClient())
    result = await proto.pyth_price("BTC")
    assert result is None


# ---------------------------------------------------------------------------
# classify_optimism — Pyth telemetry extension
# ---------------------------------------------------------------------------


@dataclass
class _StubReserve:
    symbol: str
    paused: bool = False
    frozen: bool = False
    utilization: float = 0.0


@dataclass
class _StubOverview:
    reserves: list[_StubReserve]


@dataclass
class _StubPythReading:
    symbol: str
    stale: bool


def test_classify_optimism_warning_on_stale_pyth_with_aave_healthy() -> None:
    """Aave nominal + Pyth stale on a major => WARNING (degraded redundancy)."""
    overview = _StubOverview(
        reserves=[_StubReserve(symbol="WETH", utilization=0.4)]
    )
    pyth = [
        _StubPythReading(symbol="BTC", stale=True),
        _StubPythReading(symbol="ETH", stale=False),
    ]
    verdict = classify_optimism(overview, pyth_readings=pyth)
    assert verdict.severity == "WARNING"
    assert "BTC" in verdict.pyth_stale_symbols
    assert "ETH" in verdict.pyth_fresh_symbols
    assert any("Pyth fallback stale" in r for r in verdict.reasons)


def test_classify_optimism_block_from_aave_not_overridden_by_fresh_pyth() -> None:
    """A BLOCK on Aave never downgrades just because Pyth is healthy."""
    overview = _StubOverview(
        reserves=[_StubReserve(symbol="USDC", paused=True, utilization=0.95)]
    )
    pyth = [_StubPythReading(symbol="BTC", stale=False)]
    verdict = classify_optimism(overview, pyth_readings=pyth)
    assert verdict.severity == "BLOCK"
    assert verdict.pyth_fresh_symbols == ["BTC"]


def test_classify_optimism_pyth_telemetry_appears_in_healthy_reasons() -> None:
    """Operators want to see Pyth-fresh-on-X next to 'chain healthy'."""
    overview = _StubOverview(
        reserves=[_StubReserve(symbol="WETH", utilization=0.4)]
    )
    pyth = [
        _StubPythReading(symbol="BTC", stale=False),
        _StubPythReading(symbol="ETH", stale=False),
    ]
    verdict = classify_optimism(overview, pyth_readings=pyth)
    assert verdict.severity == "HEALTHY"
    # First reason is the lend-side; second is the Pyth-fresh telemetry.
    assert any("Pyth fallback fresh" in r for r in verdict.reasons)
    assert verdict.pyth_fresh_symbols == ["BTC", "ETH"]
    assert verdict.pyth_stale_symbols == []


def test_classify_optimism_no_pyth_arg_keeps_pre_pyth_behavior() -> None:
    """Backwards-compat: classify_optimism(overview) works without Pyth arg."""
    overview = _StubOverview(
        reserves=[_StubReserve(symbol="WETH", utilization=0.4)]
    )
    verdict = classify_optimism(overview)
    assert verdict.severity == "HEALTHY"
    assert verdict.pyth_fresh_symbols == []
    assert verdict.pyth_stale_symbols == []


# ---------------------------------------------------------------------------
# evaluate_optimism_chain_health — Aave-revert fallback path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_falls_back_to_pyth_when_aave_reverts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real failure mode: Aave oracle reverts → fall through to Pyth WARNING."""

    class FakeProtocols:
        def __init__(self, client: object) -> None:
            self._client = client
            self.pyth = _FakePythReg(
                {"BTC": _StubPythReading(symbol="BTC", stale=False)}
            )

        async def lend_overview(self) -> Any:
            raise RuntimeError("execution reverted (Aave oracle)")

    class _FakePythReg:
        def __init__(self, readings: dict[str, Any]) -> None:
            self._r = readings

        async def fetch_price(self, sym: str) -> Any:
            if sym not in self._r:
                raise LookupError(sym)
            return self._r[sym]

    import lib.chains.optimism.protocols as proto_module

    monkeypatch.setattr(proto_module, "OptimismProtocols", FakeProtocols)

    verdict = await evaluate_optimism_chain_health(object())
    assert verdict.severity == "WARNING"
    assert verdict.chain_id == 10
    assert "BTC" in verdict.pyth_fresh_symbols
    assert any("Aave read failed" in r for r in verdict.reasons)
    assert any("Pyth fallback active" in r for r in verdict.reasons)


@pytest.mark.asyncio
async def test_evaluate_reraises_when_aave_fails_and_pyth_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both sources fail, surface the original Aave error to the dispatcher."""

    class _NullPyth:
        async def fetch_price(self, sym: str) -> Any:
            raise RuntimeError("pyth also broken")

    class FakeProtocols:
        def __init__(self, client: object) -> None:
            self.pyth = _NullPyth()

        async def lend_overview(self) -> Any:
            raise RuntimeError("execution reverted (Aave oracle)")

    import lib.chains.optimism.protocols as proto_module

    monkeypatch.setattr(proto_module, "OptimismProtocols", FakeProtocols)

    with pytest.raises(RuntimeError, match="Aave oracle"):
        await evaluate_optimism_chain_health(object())


def test_pyth_probe_symbols_covers_majors() -> None:
    """Sanity-pin the symbols the gate probes — changing this changes alerts."""
    assert "BTC" in PYTH_PROBE_SYMBOLS
    assert "ETH" in PYTH_PROBE_SYMBOLS
    assert "USDC" in PYTH_PROBE_SYMBOLS


# ---------------------------------------------------------------------------
# Live integration tests (skip-by-default; gated by env var)
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
                "User-Agent": "sapphire-optimism-pyth-test/1.0",
            },
        )
        with self._urllib.urlopen(req, timeout=30) as resp:
            payload = _json.loads(resp.read())
        if "error" in payload:
            raise RuntimeError(f"RPC error: {payload['error']}")
        return payload.get("result")


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_OPTIMISM_INTEGRATION") != "1",
    reason="set SAPPHIRE_OPTIMISM_INTEGRATION=1 to hit live Optimism Pyth",
)
async def test_live_pyth_btc_price_in_plausible_range() -> None:
    """Hit real Optimism Pyth and confirm BTC/USD is in [$50k, $200k].

    Wide range on purpose — this is "is the feed alive at all", not a
    price-prediction test.
    """
    rpc_url = os.getenv("SAPPHIRE_OPTIMISM_RPC", "https://mainnet.optimism.io")
    reg = PythRegistry(HttpClient(rpc_url))

    record = await reg.fetch_price("BTC")
    assert record.usd > Decimal("50000"), f"BTC suspiciously low: {record.usd}"
    assert record.usd < Decimal("200000"), f"BTC suspiciously high: {record.usd}"
    age_s = time.time() - record.publish_time
    print(
        f"\n[live] Pyth BTC/USD on Optimism = ${record.usd} "
        f"(age {age_s:.1f}s, stale={record.stale})"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_OPTIMISM_INTEGRATION") != "1",
    reason="set SAPPHIRE_OPTIMISM_INTEGRATION=1 to hit live Optimism Pyth",
)
async def test_live_optimism_protocols_pyth_price_eth() -> None:
    """End-to-end: OptimismProtocols(client).pyth_price('ETH') returns a sane Decimal."""
    from lib.chains.optimism.protocols import OptimismProtocols

    rpc_url = os.getenv("SAPPHIRE_OPTIMISM_RPC", "https://mainnet.optimism.io")
    proto = OptimismProtocols(HttpClient(rpc_url))
    usd = await proto.pyth_price("ETH")
    assert usd is not None, "Pyth ETH price returned None on live RPC"
    assert usd > Decimal("1000"), f"ETH suspiciously low: {usd}"
    assert usd < Decimal("10000"), f"ETH suspiciously high: {usd}"
    print(f"\n[live] OptimismProtocols.pyth_price('ETH') = ${usd}")
