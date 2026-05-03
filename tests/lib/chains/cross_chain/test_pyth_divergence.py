"""Unit + gated-integration tests for the cross-chain Pyth divergence detector.

The detector composes per-chain Pyth registries (megaeth / arbitrum /
optimism). Tests here mock the registries so we pin the classifier
rules + the divergence math without hitting the network. One gated
test at the bottom hits Arbitrum + (when present) MegaETH / Optimism
mainnets to prove the pipeline composes against real on-chain Pyth
caches.

Severity bands under test (basis points = bps; 100 bps == 1 %):

* ``NORMAL``       — max divergence < 20 bps  (no signal returned)
* ``OPPORTUNITY``  — 20 bps ≤ max divergence < 100 bps
* ``EXTREME``      — max divergence ≥ 100 bps
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from lib.chains.cross_chain.pyth_divergence import (
    DEFAULT_TOP_ASSETS,
    EXTREME_DIVERGENCE_BPS,
    MIN_SIGNAL_DIVERGENCE_BPS,
    SEVERITY_EXTREME,
    SEVERITY_NORMAL,
    SEVERITY_OPPORTUNITY,
    CrossChainPythScanner,
    PythDivergenceSignal,
)

# ---------------------------------------------------------------------------
# Test stubs — mirror the duck-typed surface scanner depends on.
# ---------------------------------------------------------------------------


@dataclass
class _StubPrice:
    """Mirrors the fields scanner reads off ``PythRegistryPrice``."""

    symbol: str
    price_id: str
    usd: Decimal
    publish_time: int
    stale: bool = False


class _StubRegistry:
    """Stand-in for a Pyth registry.

    Only ``fetch_price`` and ``_address`` are consumed by the scanner.
    ``raises`` lets a test simulate an RPC failure on a single chain
    (graceful-degradation path). ``unknown`` lets a test simulate a
    chain that doesn't carry the requested feed (LookupError path).
    """

    def __init__(
        self,
        symbol_prices: dict[str, _StubPrice] | None = None,
        *,
        address: str = "0xff1a0f4744e8582DF1aE09D5611b887B6a12925C",
        raises: Exception | None = None,
    ) -> None:
        self._prices = dict(symbol_prices or {})
        self._address = address
        self._raises = raises
        self.calls: list[str] = []

    async def fetch_price(self, symbol: str) -> _StubPrice:
        self.calls.append(symbol)
        if self._raises is not None:
            raise self._raises
        sym = symbol.upper()
        if sym not in self._prices:
            raise LookupError(f"no Pyth priceId registered for symbol {symbol!r}")
        return self._prices[sym]


def _price(
    symbol: str,
    usd: str | Decimal,
    *,
    publish_time: int = 1_761_000_000,
    stale: bool = False,
) -> _StubPrice:
    return _StubPrice(
        symbol=symbol,
        price_id="0x" + "ab" * 32,
        usd=Decimal(str(usd)),
        publish_time=publish_time,
        stale=stale,
    )


# ---------------------------------------------------------------------------
# Constants pin
# ---------------------------------------------------------------------------


def test_thresholds_are_pinned() -> None:
    """Every downstream consumer keys behaviour on these constants."""
    assert MIN_SIGNAL_DIVERGENCE_BPS == Decimal("20")
    assert EXTREME_DIVERGENCE_BPS == Decimal("100")
    assert SEVERITY_NORMAL == "NORMAL"
    assert SEVERITY_OPPORTUNITY == "OPPORTUNITY"
    assert SEVERITY_EXTREME == "EXTREME"
    assert DEFAULT_TOP_ASSETS == ("BTC", "ETH", "SOL", "USDC", "USDT")


# ---------------------------------------------------------------------------
# scan_asset — happy paths + severity bands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_divergence_returns_none() -> None:
    """Two chains within 5 bps → no signal (NORMAL band)."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00")})
    op = _StubRegistry({"BTC": _price("BTC", "76038.00")})  # ~5 bps higher
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("BTC")
    assert sig is None, "divergence <20bps must not emit a signal"


@pytest.mark.asyncio
async def test_50bps_divergence_emits_opportunity_signal() -> None:
    """50 bps gap → OPPORTUNITY band."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00", publish_time=1_761_000_000)})
    op = _StubRegistry({"BTC": _price("BTC", "76380.00", publish_time=1_761_000_010)})
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("BTC")
    assert sig is not None
    assert sig.severity == SEVERITY_OPPORTUNITY
    # (76380 - 76000) / 76000 * 10000 = 50.0
    assert sig.max_divergence_bps == Decimal("50")
    # Optimism has the larger publish_time → freshest. Arbitrum stalest.
    assert sig.freshest_chain == "Optimism"
    assert sig.stalest_chain == "Arbitrum"


@pytest.mark.asyncio
async def test_150bps_divergence_emits_extreme_signal() -> None:
    """150 bps gap → EXTREME band."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00")})
    op = _StubRegistry({"BTC": _price("BTC", "77140.00")})
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("BTC")
    assert sig is not None
    assert sig.severity == SEVERITY_EXTREME
    assert sig.max_divergence_bps == Decimal("150")


@pytest.mark.asyncio
async def test_20bps_boundary_is_inclusive_for_signal_emission() -> None:
    """A divergence of exactly MIN_SIGNAL_DIVERGENCE_BPS must emit
    (gate is ``< MIN``, so 20 → emit OPPORTUNITY)."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00")})
    op = _StubRegistry({"BTC": _price("BTC", "76152.00")})  # exactly 20 bps
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("BTC")
    assert sig is not None
    assert sig.max_divergence_bps == Decimal("20")
    assert sig.severity == SEVERITY_OPPORTUNITY


@pytest.mark.asyncio
async def test_100bps_boundary_is_extreme() -> None:
    """A divergence of exactly EXTREME_DIVERGENCE_BPS must classify as
    EXTREME (gate is ``< EXTREME``, so 100 → EXTREME)."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00")})
    op = _StubRegistry({"BTC": _price("BTC", "76760.00")})  # exactly 100 bps
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("BTC")
    assert sig is not None
    assert sig.max_divergence_bps == Decimal("100")
    assert sig.severity == SEVERITY_EXTREME


# ---------------------------------------------------------------------------
# Insufficient coverage paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_only_on_one_chain_returns_none() -> None:
    """Only Arbitrum has the symbol → no cross-chain comparison
    possible → no signal."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00")})
    op = _StubRegistry({})  # empty registry → LookupError
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("BTC")
    assert sig is None


@pytest.mark.asyncio
async def test_one_chain_rpc_fails_signal_still_emits_with_chains_unavailable() -> None:
    """One chain dies, two remaining have a real divergence → signal
    surfaces the failed chain in chains_unavailable."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00")})
    op = _StubRegistry({"BTC": _price("BTC", "76760.00")})
    mega = _StubRegistry(raises=RuntimeError("RPC down on MegaETH"))
    scanner = CrossChainPythScanner(
        megaeth_pyth=mega, arbitrum_pyth=arb, optimism_pyth=op
    )
    sig = await scanner.scan_asset("BTC")
    assert sig is not None
    assert sig.max_divergence_bps == Decimal("100")
    assert sig.chains_unavailable == ["MegaETH"]
    assert set(sig.chains.keys()) == {"Arbitrum", "Optimism"}


@pytest.mark.asyncio
async def test_two_chains_fail_returns_none_not_exception() -> None:
    """Two chains fail, one chain succeeds → not enough for a
    divergence (need >=2). Must return ``None`` cleanly."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000.00")})
    op = _StubRegistry(raises=RuntimeError("Optimism RPC down"))
    mega = _StubRegistry(raises=RuntimeError("MegaETH RPC down"))
    scanner = CrossChainPythScanner(
        megaeth_pyth=mega, arbitrum_pyth=arb, optimism_pyth=op
    )
    sig = await scanner.scan_asset("BTC")
    assert sig is None


# ---------------------------------------------------------------------------
# Staleness handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_price_still_surfaces_with_any_stale_flag() -> None:
    """Stale prices are not silently dropped — the signal surfaces
    with ``any_stale=True`` so the operator can discount the
    divergence (it may close the moment a keeper refreshes)."""
    arb = _StubRegistry(
        {"BTC": _price("BTC", "76000.00", publish_time=1_761_000_000, stale=False)}
    )
    op = _StubRegistry(
        {"BTC": _price("BTC", "76760.00", publish_time=1_760_000_000, stale=True)}
    )
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("BTC")
    assert sig is not None
    assert sig.any_stale is True
    assert sig.severity == SEVERITY_EXTREME
    # Stalest = lowest publish_time = Optimism (1_760_000_000)
    assert sig.stalest_chain == "Optimism"
    assert sig.freshest_chain == "Arbitrum"
    # Per-chain stale flag preserved
    assert sig.chains["Arbitrum"]["stale"] is False
    assert sig.chains["Optimism"]["stale"] is True


@pytest.mark.asyncio
async def test_freshest_stalest_resolved_by_publish_time() -> None:
    """Freshest = max publish_time; stalest = min. Three-chain case."""
    arb = _StubRegistry(
        {"BTC": _price("BTC", "76000.00", publish_time=2000)},
        address="0xARB",
    )
    op = _StubRegistry(
        {"BTC": _price("BTC", "76200.00", publish_time=3000)},
        address="0xOP",
    )
    mega = _StubRegistry(
        {"BTC": _price("BTC", "76152.00", publish_time=1000)},
        address="0xMEGA",
    )
    scanner = CrossChainPythScanner(
        megaeth_pyth=mega, arbitrum_pyth=arb, optimism_pyth=op
    )
    sig = await scanner.scan_asset("BTC")
    assert sig is not None
    assert sig.freshest_chain == "Optimism"
    assert sig.stalest_chain == "MegaETH"
    # Source addresses propagated for dashboard provenance.
    assert sig.chains["Arbitrum"]["source_address"] == "0xARB"
    assert sig.chains["Optimism"]["source_address"] == "0xOP"
    assert sig.chains["MegaETH"]["source_address"] == "0xMEGA"


# ---------------------------------------------------------------------------
# Decimal precision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prices_preserved_as_decimal_in_signal() -> None:
    """Pyth's int64 * 10**expo precision must survive into the signal
    (no float rounding); test asserts Decimal type and exact value."""
    arb = _StubRegistry({"ETH": _price("ETH", "3456.789012")})
    op = _StubRegistry({"ETH": _price("ETH", "3500.00")})
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("ETH")
    assert sig is not None
    assert isinstance(sig.chains["Arbitrum"]["price"], Decimal)
    assert sig.chains["Arbitrum"]["price"] == Decimal("3456.789012")
    assert isinstance(sig.max_divergence_bps, Decimal)


@pytest.mark.asyncio
async def test_symbol_uppercased_in_signal() -> None:
    """Asset symbol on the signal is canonicalized to uppercase."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000")})
    op = _StubRegistry({"BTC": _price("BTC", "76500")})
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    sig = await scanner.scan_asset("btc")
    assert sig is not None
    assert sig.asset == "BTC"


# ---------------------------------------------------------------------------
# scan_top_assets ordering + filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_top_assets_returns_sorted_by_divergence_desc() -> None:
    """Sharper opportunity surfaces first."""
    # BTC: 50 bps; ETH: 200 bps; SOL: 30 bps; USDC: 0 (won't emit)
    arb = _StubRegistry(
        {
            "BTC": _price("BTC", "76000"),
            "ETH": _price("ETH", "3000"),
            "SOL": _price("SOL", "150"),
            "USDC": _price("USDC", "1.0000"),
            "USDT": _price("USDT", "1.0000"),
        }
    )
    op = _StubRegistry(
        {
            "BTC": _price("BTC", "76380"),  # 50 bps
            "ETH": _price("ETH", "3060"),  # 200 bps
            "SOL": _price("SOL", "150.45"),  # 30 bps
            "USDC": _price("USDC", "1.00005"),  # 0.5 bps → no signal
            "USDT": _price("USDT", "1.0000"),  # 0 bps → no signal
        }
    )
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    signals = await scanner.scan_top_assets(n=5)
    assert [s.asset for s in signals] == ["ETH", "BTC", "SOL"]
    # Descending divergence order
    bps_list = [s.max_divergence_bps for s in signals]
    assert bps_list == sorted(bps_list, reverse=True)


@pytest.mark.asyncio
async def test_scan_top_assets_skips_when_only_one_chain_has_it() -> None:
    """Asset present on only one chain is silently skipped."""
    arb = _StubRegistry(
        {
            "BTC": _price("BTC", "76000"),
            "ETH": _price("ETH", "3000"),  # only on Arbitrum
        }
    )
    op = _StubRegistry({"BTC": _price("BTC", "76500")})  # 65.79 bps
    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=op)
    signals = await scanner.scan_top_assets(n=5)
    # Only BTC emitted; ETH is skipped (not a real cross-chain situation).
    assert [s.asset for s in signals] == ["BTC"]


@pytest.mark.asyncio
async def test_scan_top_assets_per_asset_failure_does_not_break_scan() -> None:
    """If one asset's scan raises, the loop logs and moves on — other
    assets still surface."""
    # Arbitrum returns valid; Optimism throws on ETH only.
    arb = _StubRegistry(
        {
            "BTC": _price("BTC", "76000"),
            "ETH": _price("ETH", "3000"),
        }
    )

    class _SelectiveOptimism:
        _address = "0xOP"

        async def fetch_price(self, symbol: str) -> _StubPrice:
            if symbol.upper() == "ETH":
                raise RuntimeError("simulated boom on ETH only")
            if symbol.upper() == "BTC":
                return _price("BTC", "76760")
            raise LookupError(f"no priceId for {symbol}")

    scanner = CrossChainPythScanner(arbitrum_pyth=arb, optimism_pyth=_SelectiveOptimism())
    signals = await scanner.scan_top_assets(n=5)
    # BTC succeeds at 100 bps. ETH errors → ETH still produces a signal
    # because Optimism's failure is captured on chains_unavailable, but
    # Optimism failing means only Arbitrum has ETH → too few chains →
    # ETH skipped. Final list = BTC only.
    assert [s.asset for s in signals] == ["BTC"]


# ---------------------------------------------------------------------------
# to_dict + JSON round-trip
# ---------------------------------------------------------------------------


def test_signal_to_dict_strings_decimals_and_round_trips_through_json() -> None:
    """to_dict must produce a JSON-safe payload."""
    sig = PythDivergenceSignal(
        asset="BTC",
        chains={
            "Arbitrum": {
                "price": Decimal("76000.00"),
                "publish_time": 1_761_000_000,
                "stale": False,
                "source_address": "0xff1a",
            },
            "Optimism": {
                "price": Decimal("76760.00"),
                "publish_time": 1_761_000_005,
                "stale": False,
                "source_address": "0xff1a",
            },
        },
        max_divergence_bps=Decimal("100"),
        freshest_chain="Optimism",
        stalest_chain="Arbitrum",
        severity=SEVERITY_EXTREME,
        chains_unavailable=["MegaETH"],
        any_stale=False,
    )
    d = sig.to_dict()
    assert d["asset"] == "BTC"
    assert d["severity"] == "EXTREME"
    assert d["max_divergence_bps"] == "100"
    # Per-chain values must also be strings.
    assert d["chains"]["Arbitrum"]["price"] == "76000.00"
    assert d["chains"]["Optimism"]["publish_time"] == 1_761_000_005
    assert d["chains_unavailable"] == ["MegaETH"]
    assert d["any_stale"] is False
    # Confirm round-trip-through-json works (no Decimals leaked).
    import json

    payload = json.dumps(d)
    assert '"BTC"' in payload
    parsed = json.loads(payload)
    assert parsed["asset"] == "BTC"


# ---------------------------------------------------------------------------
# Empty / partial-deployment scanner construction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_with_zero_chains_returns_none_for_any_scan() -> None:
    """Defensive: empty scanner is constructible (e.g. all imports
    failed) and just returns None for every scan rather than raising."""
    scanner = CrossChainPythScanner()
    sig = await scanner.scan_asset("BTC")
    assert sig is None
    signals = await scanner.scan_top_assets(n=5)
    assert signals == []


@pytest.mark.asyncio
async def test_scanner_with_one_chain_returns_none() -> None:
    """One chain wired = no cross-chain comparison possible."""
    arb = _StubRegistry({"BTC": _price("BTC", "76000")})
    scanner = CrossChainPythScanner(arbitrum_pyth=arb)
    sig = await scanner.scan_asset("BTC")
    assert sig is None


# ---------------------------------------------------------------------------
# Live mainnet integration — gated. Hits the available Pyth deployments.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_CROSS_CHAIN_INTEGRATION") != "1",
    reason="set SAPPHIRE_CROSS_CHAIN_INTEGRATION=1 to run live cross-chain RPC test",
)
async def test_live_scan_top_assets_arbitrum_plus_any_other() -> None:
    """Live: scan available Pyth mainnets for BTC/ETH/SOL/USDC/USDT.

    Arbitrum Pyth is required (lib.chains.arbitrum.contracts.pyth_oracle
    is the prerequisite for this PR). MegaETH and Optimism Pyth are
    parallel work; if either lands during PR review the test picks
    them up automatically. With only one chain wired the scanner
    returns no signals, which is itself a correct result."""
    from lib.chains.arbitrum.client import ArbitrumClient
    from lib.chains.arbitrum.contracts.pyth_oracle import PythRegistry as ArbPyth

    megaeth_pyth: Any | None = None
    optimism_pyth: Any | None = None

    # MegaETH Pyth ships in a parallel branch (PR #608); pick it up if
    # it has merged but tolerate ImportError gracefully.
    try:
        from lib.chains.megaeth.client import MegaETHClient  # noqa: PLC0415
        from lib.chains.megaeth.contracts.pyth_oracle import (  # noqa: PLC0415
            PythRegistry as MegaPyth,
        )

        mega_client = MegaETHClient()
        megaeth_pyth = MegaPyth(mega_client)
    except Exception:  # noqa: BLE001 — best effort; integration tolerant
        megaeth_pyth = None

    # Optimism Pyth ditto.
    try:
        from lib.chains.optimism.client import OptimismClient  # noqa: PLC0415

        from lib.chains.optimism.contracts.pyth_oracle import (  # noqa: PLC0415
            PythRegistry as OpPyth,
        )

        op_client = OptimismClient()
        optimism_pyth = OpPyth(op_client)
    except Exception:  # noqa: BLE001
        optimism_pyth = None

    async with ArbitrumClient() as arb_client:
        scanner = CrossChainPythScanner(
            megaeth_pyth=megaeth_pyth,
            arbitrum_pyth=ArbPyth(arb_client),
            optimism_pyth=optimism_pyth,
        )
        signals = await scanner.scan_top_assets(n=5)

    print("\nLive cross-chain Pyth divergence scan:")
    for s in signals:
        chains_str = ", ".join(
            f"{c}=${v['price']:.2f}@{v['publish_time']}{'(stale)' if v['stale'] else ''}"
            for c, v in s.chains.items()
        )
        print(
            f"  {s.asset:6s} max_div={s.max_divergence_bps:>10} bps "
            f"severity={s.severity:11s} freshest={s.freshest_chain} "
            f"stalest={s.stalest_chain} any_stale={s.any_stale} "
            f"[{chains_str}]"
        )

    assert isinstance(signals, list)
    assert all(isinstance(s, PythDivergenceSignal) for s in signals)


def _hush_unused() -> Any:
    return DEFAULT_TOP_ASSETS, EXTREME_DIVERGENCE_BPS, MIN_SIGNAL_DIVERGENCE_BPS
