"""Unit tests for the perps_* extension on ArbitrumProtocols facade.

Stubs the underlying GmxV2Arbitrum + GmxPriceAdapter so the facade is
exercised end-to-end without RPC. Confirms the new dataclasses
(PerpsOverview / PerpsMarketState) and the four append-only methods
(perps_overview, perps_market_info, perps_funding_rate_apr, perps_oi_skew)
behave as advertised, including the unpriced-market surfacing path.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from lib.chains.arbitrum.contracts.gmx_price_adapter import PriceUnavailable
from lib.chains.arbitrum.contracts.gmx_v2 import Market, MarketInfo
from lib.chains.arbitrum.protocols import (
    ArbitrumProtocols,
    PerpsMarketState,
    PerpsOverview,
)
from lib.chains.arbitrum.registry import ProtocolEntry, ProtocolRegistry

# ---------- helpers ----------------------------------------------------------


def _market(name: str, idx: str = "b") -> Market:
    # Use the index char as the discriminator everywhere so each
    # _market() call yields a unique market_token (and we can use
    # market_token as a dict key in stubs without collisions).
    return Market(
        market_token="0x" + (idx * 40),
        index_token="0x" + (idx * 40),
        long_token="0x" + ("c" * 40),
        short_token="0x" + ("d" * 40),
        name=name,
    )


def _info(*, ff: int, lps: bool, oi_l: int, oi_s: int, disabled: bool = False) -> MarketInfo:
    return MarketInfo(
        market=_market("x"),
        funding_factor_per_second=ff,
        longs_pay_shorts=lps,
        borrowing_factor_long=0,
        borrowing_factor_short=0,
        open_interest_long=oi_l,
        open_interest_short=oi_s,
        is_disabled=disabled,
    )


class StubGmx:
    def __init__(
        self,
        markets: list[Market],
        info_by_market_token: dict[str, MarketInfo],
        info_raises: dict[str, Exception] | None = None,
    ) -> None:
        self._markets = markets
        self._info = info_by_market_token
        self._raises = info_raises or {}

    async def list_markets(self, *, start: int = 0, end: int = 200) -> list[Market]:
        return list(self._markets)

    async def get_market(self, market_key: str) -> Market:
        for m in self._markets:
            if m.market_token == market_key:
                return m
        raise LookupError(market_key)

    async def market_info(self, market: str, prices: Any) -> MarketInfo:
        if market in self._raises:
            raise self._raises[market]
        return self._info[market]

    async def funding_rate_apr(self, market: str, prices: Any) -> Decimal:
        info = self._info[market]
        # Re-use the facade's helper logic via a small inline copy.
        from lib.chains.arbitrum.contracts.gmx_v2 import GmxV2Arbitrum

        return GmxV2Arbitrum._funding_apr_from_info(info)

    async def oi_skew(self, market: str, prices: Any) -> Decimal:
        from lib.chains.arbitrum.contracts.gmx_v2 import GmxV2Arbitrum

        return GmxV2Arbitrum._oi_skew_from_info(self._info[market])


class StubAdapter:
    def __init__(self, unpriced_market_tokens: set[str] | None = None) -> None:
        self._unpriced = unpriced_market_tokens or set()

    async def market_prices(self, market: Market) -> Any:
        if market.market_token in self._unpriced:
            raise PriceUnavailable(f"no price for {market.market_token}")
        return ((1, 1), (1, 1), (1, 1))


def _registry_with_gmx() -> ProtocolRegistry:
    e = ProtocolEntry(
        key="gmx_v2",
        name="GMX V2",
        category="perps",
        priority=1,
        status="active",
        docs_url="",
        addresses={
            "reader": "0x" + "1" * 40,
            "data_store": "0x" + "2" * 40,
            "event_emitter": "0x" + "3" * 40,
        },
    )
    aave = ProtocolEntry(
        key="aave_v3",
        name="Aave V3",
        category="lending",
        priority=1,
        status="active",
        docs_url="",
        addresses={
            "pool": "0x" + "4" * 40,
            "pool_addresses_provider": "0x" + "5" * 40,
            "oracle": "0x" + "6" * 40,
            "ui_pool_data_provider": "0x" + "7" * 40,
            "protocol_data_provider": "0x" + "8" * 40,
        },
    )
    return ProtocolRegistry({"gmx_v2": e, "aave_v3": aave})


def _build_facade(
    monkeypatch: pytest.MonkeyPatch,
    gmx: StubGmx,
    adapter: StubAdapter,
) -> ArbitrumProtocols:
    proto = ArbitrumProtocols(client=object(), registry=_registry_with_gmx())
    monkeypatch.setattr(proto, "_gmx", lambda venue="gmx_v2": gmx)  # type: ignore[method-assign]
    monkeypatch.setattr(
        proto,
        "_price_adapter",
        lambda lend_venue="aave_v3": adapter,  # type: ignore[arg-type]
    )
    return proto


# ---------- perps_overview ---------------------------------------------------


@pytest.mark.asyncio
async def test_perps_overview_aggregates_two_markets(monkeypatch: pytest.MonkeyPatch) -> None:
    m1 = _market("ETH-USD", "1")
    m2 = _market("BTC-USD", "2")
    info1 = _info(ff=10**26, lps=True, oi_l=10**33, oi_s=10**33)
    info2 = _info(ff=2 * 10**26, lps=False, oi_l=10**32, oi_s=2 * 10**32)
    gmx = StubGmx([m1, m2], {m1.market_token: info1, m2.market_token: info2})
    adapter = StubAdapter()
    proto = _build_facade(monkeypatch, gmx, adapter)

    overview = await proto.perps_overview()
    assert isinstance(overview, PerpsOverview)
    assert overview.venue == "gmx_v2"
    assert overview.market_count == 2
    assert overview.priced_count == 2
    assert overview.unpriced_count == 0
    assert len(overview.markets) == 2
    assert all(s.state == "ok" for s in overview.markets)
    # OI total should be in plain USD (not 1e30-scaled).
    for s in overview.markets:
        assert s.oi_total_usd is not None
        assert s.oi_total_usd > Decimal(0)


@pytest.mark.asyncio
async def test_perps_overview_surfaces_unpriced_market(monkeypatch: pytest.MonkeyPatch) -> None:
    m1 = _market("ETH-USD", "1")
    m_exotic = _market("EXOTIC-USD", "9")
    info1 = _info(ff=0, lps=True, oi_l=0, oi_s=0)
    gmx = StubGmx([m1, m_exotic], {m1.market_token: info1})
    adapter = StubAdapter(unpriced_market_tokens={m_exotic.market_token})
    proto = _build_facade(monkeypatch, gmx, adapter)

    overview = await proto.perps_overview()
    assert overview.market_count == 2
    assert overview.priced_count == 1
    assert overview.unpriced_count == 1
    states = {s.market.name: s.state for s in overview.markets}
    assert states["ETH-USD"] == "ok"
    assert states["EXOTIC-USD"] == "unpriced"


@pytest.mark.asyncio
async def test_perps_overview_captures_market_info_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    m_bad = _market("BAD-USD", "f")
    gmx = StubGmx(
        [m_bad],
        {},
        info_raises={m_bad.market_token: RuntimeError("rpc-fail")},
    )
    adapter = StubAdapter()
    proto = _build_facade(monkeypatch, gmx, adapter)

    overview = await proto.perps_overview()
    assert overview.market_count == 1
    assert overview.priced_count == 0  # error doesn't count as priced
    state = overview.markets[0]
    assert state.state == "error"
    assert state.reason and "rpc-fail" in state.reason


@pytest.mark.asyncio
async def test_perps_overview_marks_disabled_state(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _market("PAUSED", "5")
    info = _info(ff=0, lps=True, oi_l=0, oi_s=0, disabled=True)
    gmx = StubGmx([m], {m.market_token: info})
    proto = _build_facade(monkeypatch, gmx, StubAdapter())

    overview = await proto.perps_overview()
    state = overview.markets[0]
    assert state.state == "disabled"
    # priced_count counts only "ok" — disabled is not ok.
    assert overview.priced_count == 0


# ---------- single-market helpers --------------------------------------------


@pytest.mark.asyncio
async def test_perps_market_info_routes_through_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _market("ETH-USD", "1")
    info = _info(ff=42, lps=True, oi_l=100, oi_s=200)
    gmx = StubGmx([m], {m.market_token: info})
    proto = _build_facade(monkeypatch, gmx, StubAdapter())

    out = await proto.perps_market_info(m.market_token)
    assert out is info


@pytest.mark.asyncio
async def test_perps_funding_rate_apr_returns_signed_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _market("X")
    factor = int(Decimal(10) ** 30 * Decimal("0.10") / Decimal(31_536_000))
    gmx = StubGmx([m], {m.market_token: _info(ff=factor, lps=True, oi_l=0, oi_s=0)})
    proto = _build_facade(monkeypatch, gmx, StubAdapter())
    apr = await proto.perps_funding_rate_apr(m.market_token)
    assert Decimal("0.099") < apr < Decimal("0.101")


@pytest.mark.asyncio
async def test_perps_oi_skew_returns_long_share(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _market("X")
    gmx = StubGmx([m], {m.market_token: _info(ff=0, lps=True, oi_l=300, oi_s=100)})
    proto = _build_facade(monkeypatch, gmx, StubAdapter())
    skew = await proto.perps_oi_skew(m.market_token)
    assert skew == Decimal("0.75")


# ---------- guards -----------------------------------------------------------


def test_facade_rejects_non_perps_venue_for_perps_methods() -> None:
    proto = ArbitrumProtocols(client=object(), registry=_registry_with_gmx())
    with pytest.raises(ValueError, match="not a perps venue"):
        proto._gmx("aave_v3")


def test_perps_market_state_dataclass_fields() -> None:
    s = PerpsMarketState(
        market=_market("X"),
        state="ok",
        info=None,
        funding_apr=Decimal("0.1"),
        oi_skew=Decimal("0.5"),
        oi_total_usd=Decimal("1000000"),
    )
    assert s.state == "ok"
    assert s.reason is None
