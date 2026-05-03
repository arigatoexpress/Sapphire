"""Unit tests for the Hermes-augmented Pyth divergence scanner.

The scanner under test classifies cross-chain divergence by *cause*
(stale-cache vs real off-chain move) rather than just *magnitude*.
These tests pin the classification logic across the four severity
labels and verify the scanner integrates the on-chain registries +
the Hermes client with the correct semantics.

No live network — we mock the on-chain registries and the
``PythHermesClient`` so the suite is hermetic. The Hermes client's
own integration test lives in test_pyth_hermes.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from lib.chains.cross_chain.pyth_hermes import (
    HERMES_PRICE_IDS,
    PythHermesPrice,
)
from lib.chains.cross_chain.pyth_hermes_divergence import (
    HERMES_CHAIN_NAME,
    SEVERITY_MIXED,
    SEVERITY_NORMAL,
    SEVERITY_REAL_DIVERGENCE,
    SEVERITY_STALE_CACHE,
    HermesAugmentedScanner,
    HermesAugmentedSignal,
    _classify_with_hermes,
    _max_pairwise_bps,
)


@dataclass
class _StubOnChainPrice:
    """Mimics the per-chain wrapper's PythRegistryPrice shape."""

    usd: Decimal
    publish_time: int
    stale: bool = False


def _stub_registry(symbol_to_price: dict[str, _StubOnChainPrice], *, address: str = "0xreg"):
    """Build a registry-shaped mock with async fetch_price."""
    reg = MagicMock()
    reg._address = address

    async def _fetch(symbol: str) -> _StubOnChainPrice:
        sym = symbol.upper()
        if sym not in symbol_to_price:
            raise LookupError(sym)
        return symbol_to_price[sym]

    reg.fetch_price = _fetch
    return reg


def _stub_hermes(symbol: str, price: Decimal, publish_time: int = 1_000_000):
    """Build a Hermes client mock that returns one price for one symbol."""
    client = MagicMock()
    px = PythHermesPrice(
        price=price,
        conf=Decimal("0.1"),
        expo=-8,
        publish_time=publish_time,
        vaa_bytes=b"",
    )
    client.latest_prices_by_symbol = MagicMock(return_value={symbol: px})
    return client


# -- pure classifier tests ---------------------------------------------------


class TestClassifyWithHermes:
    """``_classify_with_hermes`` — the heart of the stale-vs-real call."""

    def test_normal_when_everything_agrees(self):
        # All within 5 bps; well below the 20 bps threshold.
        on_chain = [Decimal("100"), Decimal("100.01"), Decimal("100.02")]
        hermes = Decimal("100.005")
        sev, bracketed, vs = _classify_with_hermes(on_chain, hermes)
        assert sev == SEVERITY_NORMAL
        assert bracketed is True

    def test_stale_cache_when_onchain_disagrees_but_hermes_bracketed(self):
        # 100.0 vs 100.5 — 50 bps on-chain disagreement.
        # Hermes at 100.25 is right in the middle. Pure cache lag.
        on_chain = [Decimal("100"), Decimal("100.5")]
        hermes = Decimal("100.25")
        sev, bracketed, vs = _classify_with_hermes(on_chain, hermes)
        assert sev == SEVERITY_STALE_CACHE
        assert bracketed is True

    def test_real_divergence_when_hermes_outside_and_onchain_agrees(self):
        # On-chain reads agree (both ~100.00); Hermes is 100.5 — the
        # off-chain price has moved 50 bps but no chain has refreshed.
        on_chain = [Decimal("100"), Decimal("100.01")]
        hermes = Decimal("100.5")
        sev, bracketed, vs = _classify_with_hermes(on_chain, hermes)
        assert sev == SEVERITY_REAL_DIVERGENCE
        assert bracketed is False
        # vs measured against the *farthest* on-chain read.
        assert vs > Decimal("48")  # ~49 bps

    def test_mixed_when_both_conditions_hold(self):
        # On-chain reads disagree (50 bps gap) AND Hermes is outside.
        on_chain = [Decimal("100"), Decimal("100.5")]
        hermes = Decimal("101.5")
        sev, bracketed, vs = _classify_with_hermes(on_chain, hermes)
        assert sev == SEVERITY_MIXED
        assert bracketed is False

    def test_pr621_optimism_25_day_stale_case(self):
        # Reproduce the exact failure mode PR #621 documents:
        # Optimism BTC cache is 25 days stale at ~70k while Arbitrum
        # is fresh at ~78k. Hermes reports 78k. The 1066 bps gap is
        # entirely a stale-cache artifact — Hermes would say "real
        # off-chain price is ~78k, agrees with Arbitrum".
        on_chain = [
            Decimal("70250"),  # Optimism, 25-day-stale
            Decimal("78700"),  # Arbitrum, fresh
        ]
        hermes = Decimal("78671")  # Real off-chain price
        sev, bracketed, vs = _classify_with_hermes(on_chain, hermes)
        # Hermes is bracketed (between 70250 and 78700) → STALE_CACHE,
        # not REAL_DIVERGENCE. This is the upgrade the PR delivers:
        # without Hermes the base scanner reports a 1066 bps EXTREME;
        # with Hermes we correctly attribute it to stale-cache.
        assert sev == SEVERITY_STALE_CACHE
        assert bracketed is True

    def test_empty_onchain_returns_normal(self):
        # No chains wired at all — scanner is Hermes-only. Severity
        # is NORMAL because there's no divergence to classify.
        sev, bracketed, vs = _classify_with_hermes([], Decimal("100"))
        assert sev == SEVERITY_NORMAL
        assert vs == Decimal(0)


class TestMaxPairwiseBps:
    """The shared helper used by both the base and augmented scanners."""

    def test_basic_calculation(self):
        # 100 vs 101 → 1% = 100 bps.
        assert _max_pairwise_bps([Decimal("100"), Decimal("101")]) == Decimal("100")

    def test_returns_zero_for_single_price(self):
        assert _max_pairwise_bps([Decimal("100")]) == Decimal(0)

    def test_returns_zero_for_empty(self):
        assert _max_pairwise_bps([]) == Decimal(0)

    def test_uses_min_as_denominator(self):
        # 100 vs 110 → (110-100)/100 = 1000 bps, NOT (110-100)/110.
        assert _max_pairwise_bps([Decimal("100"), Decimal("110")]) == Decimal("1000")

    def test_handles_three_prices(self):
        # max=110, min=100, gap=1000 bps. The 105 in the middle
        # doesn't change the result — it's the *max pairwise* gap.
        out = _max_pairwise_bps([Decimal("100"), Decimal("105"), Decimal("110")])
        assert out == Decimal("1000")


# -- scanner integration tests ----------------------------------------------


class TestHermesAugmentedScanner:
    """End-to-end scanner behaviour with mock registries + Hermes."""

    @pytest.mark.asyncio
    async def test_pure_hermes_no_chains(self):
        # No on-chain registries; scanner returns Hermes-only signal.
        hermes = _stub_hermes("BTC", Decimal("78700"))
        scanner = HermesAugmentedScanner(hermes=hermes)

        sig = await scanner.scan_asset("BTC")

        assert sig is not None
        assert sig.asset == "BTC"
        assert sig.hermes_price == Decimal("78700")
        assert sig.on_chain == {}
        assert sig.severity == SEVERITY_NORMAL

    @pytest.mark.asyncio
    async def test_stale_cache_reproduction(self):
        # Two chains, Hermes between them — the canonical stale-cache
        # case. Verify the scanner correctly classifies it.
        arbitrum = _stub_registry({"BTC": _StubOnChainPrice(Decimal("78700"), 1000)})
        optimism = _stub_registry({"BTC": _StubOnChainPrice(Decimal("70250"), 1)})
        hermes = _stub_hermes("BTC", Decimal("78671"))

        scanner = HermesAugmentedScanner(
            arbitrum_pyth=arbitrum,
            optimism_pyth=optimism,
            hermes=hermes,
        )

        sig = await scanner.scan_asset("BTC")

        assert sig is not None
        assert sig.severity == SEVERITY_STALE_CACHE
        assert sig.hermes_bracketed is True
        # On-chain reads disagree by ~1066 bps (the PR #621 number).
        assert sig.on_chain_max_bps > Decimal("1000")
        # Hermes vs farthest on-chain (Optimism) — sizable, but the
        # *cause* is stale-cache because Hermes is bracketed.
        assert sig.hermes_vs_onchain_max_bps > Decimal("1000")

    @pytest.mark.asyncio
    async def test_real_divergence_reproduction(self):
        # Two chains agree, Hermes outside their range → real off-chain
        # move that no chain has refreshed yet.
        arbitrum = _stub_registry({"BTC": _StubOnChainPrice(Decimal("78000"), 1000)})
        megaeth = _stub_registry({"BTC": _StubOnChainPrice(Decimal("78010"), 1000)})
        hermes = _stub_hermes("BTC", Decimal("78500"))

        scanner = HermesAugmentedScanner(
            arbitrum_pyth=arbitrum,
            megaeth_pyth=megaeth,
            hermes=hermes,
        )

        sig = await scanner.scan_asset("BTC")

        assert sig is not None
        assert sig.severity == SEVERITY_REAL_DIVERGENCE
        assert sig.hermes_bracketed is False
        # On-chain reads agree (~1.3 bps), Hermes diverges by ~64 bps.
        assert sig.on_chain_max_bps < Decimal("5")
        assert sig.hermes_vs_onchain_max_bps > Decimal("60")

    @pytest.mark.asyncio
    async def test_unknown_symbol_returns_none(self):
        scanner = HermesAugmentedScanner(hermes=_stub_hermes("BTC", Decimal("1")))
        sig = await scanner.scan_asset("NOT_A_REAL_COIN")
        assert sig is None

    @pytest.mark.asyncio
    async def test_chain_lookuperror_skipped_silently(self):
        # A chain that doesn't carry the symbol raises LookupError.
        # That should not appear in chains_unavailable — it's not a
        # failure, just absent.
        arbitrum = _stub_registry({"ETH": _StubOnChainPrice(Decimal("2300"), 1000)})  # no BTC
        hermes = _stub_hermes("BTC", Decimal("78000"))

        scanner = HermesAugmentedScanner(
            arbitrum_pyth=arbitrum,
            hermes=hermes,
        )

        sig = await scanner.scan_asset("BTC")
        assert sig is not None
        assert sig.chains_unavailable == []
        assert sig.on_chain == {}

    @pytest.mark.asyncio
    async def test_chain_runtime_error_marked_unavailable(self):
        bad = MagicMock()
        bad._address = "0xbad"

        async def _explode(symbol):
            raise RuntimeError("rpc unreachable")

        bad.fetch_price = _explode
        good = _stub_registry({"BTC": _StubOnChainPrice(Decimal("78000"), 1)})
        hermes = _stub_hermes("BTC", Decimal("78050"))

        scanner = HermesAugmentedScanner(
            arbitrum_pyth=good,
            optimism_pyth=bad,
            hermes=hermes,
        )

        sig = await scanner.scan_asset("BTC")
        assert sig is not None
        assert "Optimism" in sig.chains_unavailable
        assert "Arbitrum" in sig.on_chain

    @pytest.mark.asyncio
    async def test_hermes_failure_returns_none(self):
        # When the Hermes client itself fails, the augmented scanner
        # returns None — the caller should fall back to the base
        # scanner. The augmented flow without Hermes is meaningless.
        bad_hermes = MagicMock()
        bad_hermes.latest_prices_by_symbol = MagicMock(side_effect=RuntimeError("hermes timeout"))
        scanner = HermesAugmentedScanner(hermes=bad_hermes)
        sig = await scanner.scan_asset("BTC")
        assert sig is None

    @pytest.mark.asyncio
    async def test_scan_top_assets_sorts_by_hermes_vs_onchain(self):
        # Two assets with different Hermes-vs-onchain gaps.
        arbitrum = _stub_registry(
            {
                "BTC": _StubOnChainPrice(Decimal("78000"), 1000),
                "ETH": _StubOnChainPrice(Decimal("2300"), 1000),
            }
        )

        # Different Hermes prices per call — use side_effect to vary.
        hermes = MagicMock()
        responses = {
            "BTC": PythHermesPrice(
                price=Decimal("78010"),  # ~1 bps gap
                conf=Decimal("0"),
                expo=-8,
                publish_time=1,
                vaa_bytes=b"",
            ),
            "ETH": PythHermesPrice(
                price=Decimal("2350"),  # ~217 bps gap → larger
                conf=Decimal("0"),
                expo=-8,
                publish_time=1,
                vaa_bytes=b"",
            ),
        }

        def _by_sym(symbols, **kwargs):
            return {s: responses[s] for s in symbols if s in responses}

        hermes.latest_prices_by_symbol = _by_sym

        scanner = HermesAugmentedScanner(
            arbitrum_pyth=arbitrum,
            hermes=hermes,
        )
        sigs = await scanner.scan_top_assets(n=5)

        # ETH first (larger Hermes-vs-onchain gap), then BTC.
        assert len(sigs) >= 2
        assert sigs[0].asset == "ETH"
        assert sigs[0].hermes_vs_onchain_max_bps > sigs[1].hermes_vs_onchain_max_bps


class TestHermesAugmentedSignal:
    """The signal dataclass surface."""

    def test_to_dict_serializes_decimals(self):
        import json

        sig = HermesAugmentedSignal(
            asset="BTC",
            on_chain={
                "Arbitrum": {
                    "price": Decimal("78700"),
                    "publish_time": 1000,
                    "stale": False,
                    "source_address": "0xreg",
                }
            },
            hermes_price=Decimal("78671"),
            hermes_publish_time=2000,
            on_chain_max_bps=Decimal("0"),
            hermes_vs_onchain_max_bps=Decimal("3.69"),
            hermes_bracketed=False,
            severity=SEVERITY_NORMAL,
        )
        d = sig.to_dict()
        round_tripped = json.loads(json.dumps(d))
        assert round_tripped["asset"] == "BTC"
        assert round_tripped["hermes_price"] == "78671"
        assert round_tripped["on_chain"]["Arbitrum"]["price"] == "78700"
        assert round_tripped["hermes_vs_onchain_max_bps"] == "3.69"


def test_hermes_chain_name_constant():
    # Pin the synthetic chain label so dashboard / Telegram consumers
    # can rely on it without re-importing the symbol on every call.
    assert HERMES_CHAIN_NAME == "Hermes"


def test_hermes_price_ids_covers_all_majors():
    # A regression guard — the integration story needs all 5 majors
    # mapped or the augmented scanner can't ground-truth them.
    for sym in ("BTC", "ETH", "SOL", "USDC", "USDT"):
        assert sym in HERMES_PRICE_IDS
