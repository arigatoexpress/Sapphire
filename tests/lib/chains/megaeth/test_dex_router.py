"""Tests for the DEX best-quote router."""

from __future__ import annotations

from typing import Any

import pytest

from lib.chains.megaeth.contracts.kumbaya import KumbayaAddresses, QuoteResult
from lib.chains.megaeth.dex_router import (
    DexRoutingTable,
    SwapQuote,
    best_quote,
    quote_kumbaya,
)

WETH = "0x4200000000000000000000000000000000000006"
USDM = "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7"

ADDRS = KumbayaAddresses(
    factory="0x68b34591f662508076927803c567Cc8006988a09",
    quoter_v2="0x1F1a8dC7E138C34b503Ca080962aC10B75384a27",
    swap_router="0xE5BbEF8De2DB447a7432A47EBa58924d94eE470e",
)


class _FakeKumbaya:
    """Minimal Kumbaya stub returning canned QuoteResult per fee tier."""

    def __init__(self, by_fee: dict[int, QuoteResult | Exception]) -> None:
        self._by_fee = by_fee

    async def quote_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        amount_in: int,
        sqrt_price_limit_x96: int = 0,
    ) -> QuoteResult:
        result = self._by_fee.get(fee)
        if result is None:
            raise RuntimeError(f"no quote stubbed for fee={fee}")
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_quote_kumbaya_picks_highest_amount_out_across_fee_tiers() -> None:
    fake = _FakeKumbaya(
        {
            100: QuoteResult(
                amount_out=2200 * 10**18,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
            500: QuoteResult(
                amount_out=2255 * 10**18,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
            3000: QuoteResult(
                amount_out=2256 * 10**18,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
            10000: QuoteResult(
                amount_out=2100 * 10**18,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
        }
    )
    quote = await quote_kumbaya(fake, WETH, USDM, 10**18)  # type: ignore[arg-type]
    assert quote is not None
    assert quote.fee_pips == 3000
    assert quote.amount_out == 2256 * 10**18
    assert quote.venue == "kumbaya"
    assert quote.hops == 1


@pytest.mark.asyncio
async def test_quote_kumbaya_swallows_per_tier_failures() -> None:
    fake = _FakeKumbaya(
        {
            100: RuntimeError("no pool"),
            500: QuoteResult(
                amount_out=2255 * 10**18,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
            3000: RuntimeError("revert"),
            10000: QuoteResult(
                amount_out=2100 * 10**18,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
        }
    )
    quote = await quote_kumbaya(fake, WETH, USDM, 10**18)  # type: ignore[arg-type]
    assert quote is not None
    assert quote.fee_pips == 500


@pytest.mark.asyncio
async def test_quote_kumbaya_returns_none_when_all_tiers_fail() -> None:
    fake = _FakeKumbaya(
        {
            100: RuntimeError("a"),
            500: RuntimeError("b"),
            3000: RuntimeError("c"),
            10000: RuntimeError("d"),
        }
    )
    quote = await quote_kumbaya(fake, WETH, USDM, 10**18)  # type: ignore[arg-type]
    assert quote is None


@pytest.mark.asyncio
async def test_quote_kumbaya_skips_zero_amount_out() -> None:
    fake = _FakeKumbaya(
        {
            100: QuoteResult(
                amount_out=0,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
            500: QuoteResult(
                amount_out=1,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
            3000: QuoteResult(
                amount_out=0,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
            10000: QuoteResult(
                amount_out=0,
                sqrt_price_x96_after=1,
                initialized_ticks_crossed=0,
                gas_estimate=100_000,
            ),
        }
    )
    quote = await quote_kumbaya(fake, WETH, USDM, 10**18)  # type: ignore[arg-type]
    assert quote is not None
    assert quote.fee_pips == 500
    assert quote.amount_out == 1


@pytest.mark.asyncio
async def test_swap_quote_effective_price_zero_when_amount_in_zero() -> None:
    sq = SwapQuote(
        venue="x",
        token_in=WETH,
        token_out=USDM,
        amount_in=0,
        amount_out=0,
        fee_pips=3000,
        hops=1,
        gas_estimate=0,
    )
    assert sq.effective_price == 0


def test_dex_routing_table_register_appends_in_order() -> None:
    t = DexRoutingTable()
    assert len(t) == 0

    async def fn_a(*args: Any) -> SwapQuote | None:
        return None

    async def fn_b(*args: Any) -> SwapQuote | None:
        return None

    t.register("a", fn_a)
    t.register("b", fn_b)
    assert len(t) == 2
    venues = [v for v, _ in t.entries]
    assert venues == ["a", "b"]


@pytest.mark.asyncio
async def test_best_quote_returns_largest_amount_out() -> None:
    async def fn_low(*args: Any) -> SwapQuote | None:
        return SwapQuote(
            venue="low",
            token_in=WETH,
            token_out=USDM,
            amount_in=10**18,
            amount_out=100,
            fee_pips=3000,
            hops=1,
            gas_estimate=100,
        )

    async def fn_high(*args: Any) -> SwapQuote | None:
        return SwapQuote(
            venue="high",
            token_in=WETH,
            token_out=USDM,
            amount_in=10**18,
            amount_out=200,
            fee_pips=500,
            hops=1,
            gas_estimate=100,
        )

    t = DexRoutingTable()
    t.register("low", fn_low)
    t.register("high", fn_high)
    quote = await best_quote(t, WETH, USDM, 10**18)
    assert quote is not None
    assert quote.venue == "high"
    assert quote.amount_out == 200


@pytest.mark.asyncio
async def test_best_quote_returns_none_for_empty_table() -> None:
    quote = await best_quote(DexRoutingTable(), WETH, USDM, 10**18)
    assert quote is None


@pytest.mark.asyncio
async def test_best_quote_handles_failing_venue() -> None:
    async def fn_fail(*args: Any) -> SwapQuote | None:
        raise RuntimeError("boom")

    async def fn_ok(*args: Any) -> SwapQuote | None:
        return SwapQuote(
            venue="ok",
            token_in=WETH,
            token_out=USDM,
            amount_in=10**18,
            amount_out=42,
            fee_pips=3000,
            hops=1,
            gas_estimate=100,
        )

    t = DexRoutingTable()
    t.register("fail", fn_fail)
    t.register("ok", fn_ok)
    quote = await best_quote(t, WETH, USDM, 10**18)
    assert quote is not None
    assert quote.venue == "ok"


@pytest.mark.asyncio
async def test_best_quote_skips_none_venue() -> None:
    async def fn_none(*args: Any) -> SwapQuote | None:
        return None

    async def fn_ok(*args: Any) -> SwapQuote | None:
        return SwapQuote(
            venue="ok",
            token_in=WETH,
            token_out=USDM,
            amount_in=10**18,
            amount_out=42,
            fee_pips=3000,
            hops=1,
            gas_estimate=100,
        )

    t = DexRoutingTable()
    t.register("none", fn_none)
    t.register("ok", fn_ok)
    quote = await best_quote(t, WETH, USDM, 10**18)
    assert quote is not None
    assert quote.venue == "ok"
