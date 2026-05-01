"""Wave B.3 follow-up — facade tests for the ``perps_*`` surface.

Mocks the GmxV2 wrapper + GmxPriceAdapter behind the facade so we can
test the composition logic (PerpsOverview shaping, funding extremes
ranking, OI total) without recording fresh ABI fixtures.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.chains.megaeth.contracts.gmx_v2 import GMX_PRICE_BASE, Market, MarketInfo
from lib.chains.megaeth.protocols import (
    MarketSummary,
    MegaETHProtocols,
    PerpsOverview,
)
from lib.chains.megaeth.registry import ProtocolRegistry


def _make_market(suffix: str, name: str | None = None) -> Market:
    return Market(
        market_token="0x" + (suffix * 20)[:40],
        index_token="0x" + ("a" + suffix * 19)[:40],
        long_token="0x" + ("b" + suffix * 19)[:40],
        short_token="0x" + ("c" + suffix * 19)[:40],
        name=name or f"market-{suffix}",
    )


def _make_info(market: Market, *, funding_factor: int, longs_pay_shorts: bool, oi_long: int, oi_short: int, disabled: bool = False) -> MarketInfo:
    return MarketInfo(
        market=market,
        funding_factor_per_second=funding_factor,
        longs_pay_shorts=longs_pay_shorts,
        borrowing_factor_long=0,
        borrowing_factor_short=0,
        open_interest_long=oi_long,
        open_interest_short=oi_short,
        is_disabled=disabled,
    )


# ---------------------------------------------------------------------------
# perps_overview — lightweight (no funding)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perps_overview_lightweight_returns_summaries_only() -> None:
    fake_markets = [_make_market("12"), _make_market("34"), _make_market("56")]
    fake_gmx = MagicMock()
    fake_gmx.list_markets = AsyncMock(return_value=fake_markets)

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx):
        ov = await proto.perps_overview(include_funding=False)

    assert isinstance(ov, PerpsOverview)
    assert ov.venue == "gmx_v2"
    assert ov.market_count == 3
    assert len(ov.markets) == 3
    assert all(isinstance(s, MarketSummary) for s in ov.markets)
    # No funding overlay → no OI sum, no funding extremes.
    assert ov.total_oi_usd == Decimal(0)
    assert ov.funding_extremes == {}
    fake_gmx.list_markets.assert_awaited_once()


@pytest.mark.asyncio
async def test_perps_overview_lightweight_zero_markets() -> None:
    fake_gmx = MagicMock()
    fake_gmx.list_markets = AsyncMock(return_value=[])

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx):
        ov = await proto.perps_overview()

    assert ov.market_count == 0
    assert ov.markets == []


# ---------------------------------------------------------------------------
# perps_overview — full (with funding overlay)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perps_overview_with_funding_aggregates_oi_and_extremes() -> None:
    m1 = _make_market("12", "BTC")
    m2 = _make_market("34", "ETH")
    m3 = _make_market("56", "SOL")
    fake_markets = [m1, m2, m3]

    # OI per market (1e30-scaled USD). Use exact integer math to avoid
    # float-rounding noise in Decimal comparisons.
    one_e30 = 10**GMX_PRICE_BASE
    # BTC: 0.4 long + 0.6 short = 1.0 USD
    info_btc = _make_info(m1, funding_factor=10**20, longs_pay_shorts=False, oi_long=4 * one_e30 // 10, oi_short=6 * one_e30 // 10)
    # ETH: 2.0 long + 2.0 short = 4.0 USD
    info_eth = _make_info(m2, funding_factor=10**18, longs_pay_shorts=True, oi_long=2 * one_e30, oi_short=2 * one_e30)
    # SOL: 0.10 long + 0.05 short = 0.15 USD
    info_sol = _make_info(m3, funding_factor=10**21, longs_pay_shorts=True, oi_long=10 * one_e30 // 100, oi_short=5 * one_e30 // 100)

    fake_gmx = MagicMock()
    fake_gmx.list_markets = AsyncMock(return_value=fake_markets)
    market_info_returns = {m1.market_token: info_btc, m2.market_token: info_eth, m3.market_token: info_sol}

    async def fake_market_info(market_addr: str, prices: Any) -> MarketInfo:
        return market_info_returns[market_addr]

    fake_gmx.market_info = AsyncMock(side_effect=fake_market_info)

    fake_adapter = MagicMock()
    fake_adapter.prices_for_market = AsyncMock(return_value=((1, 1), (1, 1), (1, 1)))

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx), \
         patch.object(proto, "_price_adapter", return_value=fake_adapter):
        ov = await proto.perps_overview(include_funding=True)

    assert ov.market_count == 3
    # Total OI is summed: 1.0 + 4.0 + 0.15 = 5.15 USD (Decimal)
    assert ov.total_oi_usd == Decimal("5.15")
    # 3 markets → 3 funding extremes
    assert len(ov.funding_extremes) == 3
    # SOL has the largest abs funding factor (10^21) → first in extremes
    extremes_keys = list(ov.funding_extremes.keys())
    assert extremes_keys[0] == m3.market_token


@pytest.mark.asyncio
async def test_perps_overview_skips_markets_with_missing_oracle() -> None:
    m1 = _make_market("12", "BTC")
    m2 = _make_market("34", "ETH")
    fake_gmx = MagicMock()
    fake_gmx.list_markets = AsyncMock(return_value=[m1, m2])

    one_e30 = 10**GMX_PRICE_BASE
    info_btc = _make_info(m1, funding_factor=10**20, longs_pay_shorts=False, oi_long=4 * one_e30 // 10, oi_short=6 * one_e30 // 10)
    fake_gmx.market_info = AsyncMock(return_value=info_btc)

    fake_adapter = MagicMock()

    async def adapter_side_effect(m: Market, *, decimals: Any = None) -> Any:
        if m.market_token == m1.market_token:
            return ((1, 1), (1, 1), (1, 1))
        # m2 has no Aave oracle entry → adapter raises
        raise KeyError(f"no oracle for {m.index_token}")

    fake_adapter.prices_for_market = AsyncMock(side_effect=adapter_side_effect)

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx), \
         patch.object(proto, "_price_adapter", return_value=fake_adapter):
        ov = await proto.perps_overview(include_funding=True)

    # m1 contributes OI; m2 skipped silently but kept in summary list.
    assert ov.market_count == 2
    assert ov.total_oi_usd == Decimal("1.0")
    # Only m1 in funding_extremes (m2 was skipped)
    assert m1.market_token in ov.funding_extremes
    assert m2.market_token not in ov.funding_extremes


# ---------------------------------------------------------------------------
# perps_market_info / perps_funding_rate_apr / perps_oi_skew
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perps_market_info_delegates_to_gmx_with_adapter_prices() -> None:
    market = _make_market("12", "BTC")
    one_e30 = 10**GMX_PRICE_BASE
    info = _make_info(market, funding_factor=10**20, longs_pay_shorts=False, oi_long=one_e30, oi_short=one_e30)

    fake_gmx = MagicMock()
    fake_gmx.market_info = AsyncMock(return_value=info)

    fake_adapter = MagicMock()
    fake_adapter.prices_for_market_address = AsyncMock(return_value=((1, 1), (1, 1), (1, 1)))

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx), \
         patch.object(proto, "_price_adapter", return_value=fake_adapter):
        result = await proto.perps_market_info(market.market_token)

    assert result is info
    fake_gmx.market_info.assert_awaited_once()
    fake_adapter.prices_for_market_address.assert_awaited_once_with(market.market_token, decimals=None)


@pytest.mark.asyncio
async def test_perps_funding_rate_apr_returns_signed_decimal() -> None:
    market = _make_market("12")
    # GMX funding factor: 10^20 per second. APR = 10^20/10^30 * 31_536_000
    # = 10^-10 * 31_536_000 = 0.0031536. With longs_pay_shorts=False → negative.
    info = _make_info(market, funding_factor=10**20, longs_pay_shorts=False, oi_long=10**30, oi_short=10**30)

    fake_gmx = MagicMock()
    fake_gmx.market_info = AsyncMock(return_value=info)
    fake_adapter = MagicMock()
    fake_adapter.prices_for_market_address = AsyncMock(return_value=((1, 1), (1, 1), (1, 1)))

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx), \
         patch.object(proto, "_price_adapter", return_value=fake_adapter):
        apr = await proto.perps_funding_rate_apr(market.market_token)

    assert isinstance(apr, Decimal)
    assert apr < 0  # shorts pay longs (longs_pay_shorts=False)
    assert abs(apr) == pytest.approx(Decimal("0.0031536"), abs=Decimal("0.0000001"))


@pytest.mark.asyncio
async def test_perps_oi_skew_balanced_book() -> None:
    market = _make_market("12")
    info = _make_info(market, funding_factor=0, longs_pay_shorts=True, oi_long=10**30, oi_short=10**30)

    fake_gmx = MagicMock()
    fake_gmx.market_info = AsyncMock(return_value=info)
    fake_adapter = MagicMock()
    fake_adapter.prices_for_market_address = AsyncMock(return_value=((1, 1), (1, 1), (1, 1)))

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx), \
         patch.object(proto, "_price_adapter", return_value=fake_adapter):
        skew = await proto.perps_oi_skew(market.market_token)

    assert skew == Decimal("0.5")


@pytest.mark.asyncio
async def test_perps_oi_skew_all_long() -> None:
    market = _make_market("12")
    info = _make_info(market, funding_factor=0, longs_pay_shorts=True, oi_long=10**30, oi_short=0)

    fake_gmx = MagicMock()
    fake_gmx.market_info = AsyncMock(return_value=info)
    fake_adapter = MagicMock()
    fake_adapter.prices_for_market_address = AsyncMock(return_value=((1, 1), (1, 1), (1, 1)))

    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    with patch.object(proto, "_gmx", return_value=fake_gmx), \
         patch.object(proto, "_price_adapter", return_value=fake_adapter):
        skew = await proto.perps_oi_skew(market.market_token)

    assert skew == Decimal(1)


# ---------------------------------------------------------------------------
# Registry validation — _gmx() requires category=='dex_perps'
# ---------------------------------------------------------------------------


def test_gmx_helper_rejects_non_perps_venue() -> None:
    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    # aave_v3 is category=lending, not dex_perps → must reject.
    with pytest.raises(ValueError, match="not a perps venue"):
        proto._gmx("aave_v3")


def test_gmx_helper_resolves_gmx_v2_from_registry() -> None:
    proto = MegaETHProtocols(client=MagicMock(), registry=ProtocolRegistry.from_yaml())
    # Should not raise: gmx_v2 is registered with category=dex_perps.
    gmx = proto._gmx("gmx_v2")
    assert gmx is not None
    # Confirm the addresses came from the registry yaml.
    assert gmx.addresses.reader.lower() == "0x0f038eb4a38b08cd3c937a3256b51aa01904a684"
