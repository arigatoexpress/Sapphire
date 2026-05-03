"""Chainlink AggregatorV3Interface wrapper + canonical Arbitrum feed registry.

Lane I (PR #565) wired up the GMX V2 read layer with an Aave-only price
adapter. Of the ~60 GMX markets active on Arbitrum One, only ~4 had
fully Aave-priced index/long/short tokens (ETH, LINK, ARB, USDC) — the
other 56 surfaced as ``state="unpriced"`` and were unusable for live
funding-rate / OI signals.

This module adds Chainlink as the secondary price source. Every major
GMX index token (BTC, SOL, AVAX, DOGE, LINK, ETH) has a verified
Chainlink Data Feed on Arbitrum One that exposes USD prices via the
standard ``AggregatorV3Interface`` (``latestRoundData()`` + ``decimals()``).
Pairing Aave (primary, lender-grade) with Chainlink (fallback, broad
coverage) unlocks live BTC/SOL/AVAX/DOGE funding-rate readouts that
the Sentinel demo + Sapphire's strategy_lab need.

Why this is its own module
==========================

Chainlink reads are pure read-only HTTP RPC against published feed
proxies, so this is a cross-protocol primitive (Aave reads its own
oracle internally, but GMX, Pendle, Synthetix, and every other Arbitrum
perp/derivative venue benefits from a single Chainlink wrapper). The
``GmxPriceAdapter`` composes this in as a fallback rather than owning
the Chainlink read logic itself — so a future ``PendlePriceAdapter`` or
``SynthetixPriceAdapter`` can reuse the registry as-is.

Staleness gating
================

Chainlink feeds have a configurable "heartbeat" — for the majors on
Arbitrum, the feed updates every ~24h or sooner if the deviation
threshold (typically 0.5%) is breached. A reading older than ~1h
during normal market activity is suspicious; older than 24h is
basically guaranteed to be a stale feed (broken keeper, paused feed,
chain halt). We surface staleness as a ``stale=True`` flag on the
fetch result rather than refusing to return — Sentinel can then choose
to downweight or refuse the signal at policy level.

Decimals discipline
===================

Chainlink USD feeds on Arbitrum return prices scaled to ``10^8`` —
e.g. BTC at $76,774.81 is returned as ``7677481000000`` from
``latestRoundData().answer``. The ``decimals()`` view confirms the
scaling. We always read ``decimals()`` once at construction (or lazily
on first ``latest_price()``) and cache it — the value is immutable per
feed contract and re-reading wastes RPC. Callers that want to plug a
Chainlink price into GMX's ``Price.Props`` shape (1e30-scaled by
``10^(30 - tokenDecimals)``) should use :func:`encode_gmx_price` from
``gmx_v2.py`` against the *token decimals*, not the *feed decimals* —
the two are unrelated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..abis.fetcher import load_pinned_abi
from .base import TypedContract, _ChainCallable


#: Default staleness threshold for Chainlink feed reads (seconds).
#:
#: Chainlink majors on Arbitrum publish on a ~24h heartbeat with a
#: ~0.5% deviation trigger; under normal market conditions they update
#: far more frequently than 1h. A reading older than 1h is a soft
#: warning (markets are quiet *or* the keeper is lagging); older than
#: 24h is almost always a real failure.
DEFAULT_MAX_AGE_S = 3600  # 1 hour


#: Canonical Chainlink Data Feed addresses on Arbitrum One (chain 42161).
#:
#: Sourced from the Chainlink Data Feeds reference page and verified via
#: ``eth_getCode`` returning non-empty bytecode (verification step lives
#: in :meth:`ChainlinkRegistry.verify_addresses`, which the integration
#: tests gate live).
#:
#: Reference: https://docs.chain.link/data-feeds/price-feeds/addresses?network=arbitrum
#:
#: Symbol convention is the *underlying asset* (BTC, ETH, SOL, etc.),
#: not the wrapped ERC-20 (WBTC, WETH). The wrapped→underlying mapping
#: lives in :data:`WRAPPED_TO_UNDERLYING` so callers passing in WBTC
#: token symbols still get the BTC/USD feed.
ARBITRUM_FEEDS: dict[str, str] = {
    "BTC": "0x6ce185860a4963106506C203335A2910413708e9",
    "ETH": "0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612",
    "SOL": "0x24cEA4b8ce57cdA5058b924B9B9987992450590c",
    "AVAX": "0x8bf61728eeDCE2F32c456454d87B5d6eD6150208",
    "DOGE": "0x9A7FB1b3950837a8D9b40517626E11D4127C098C",
    "LINK": "0x86E53CF1B870786351Da77A57575e79CB55812CB",
}


#: Wrapped-token symbol → underlying-asset symbol. GMX index tokens are
#: usually the wrapped ERC-20 (WBTC, WETH) but Chainlink feeds key off
#: the underlying. This map lets ``oracle_for("WBTC")`` resolve to
#: ``ARBITRUM_FEEDS["BTC"]``.
WRAPPED_TO_UNDERLYING: dict[str, str] = {
    "WBTC": "BTC",
    "BTCB": "BTC",
    "WETH": "ETH",
    "WSOL": "SOL",
    "WAVAX": "AVAX",
    "WDOGE": "DOGE",
}


def _normalize_symbol(symbol: str) -> str:
    """Uppercase + strip a token symbol; resolve wrapped→underlying."""
    s = (symbol or "").strip().upper()
    return WRAPPED_TO_UNDERLYING.get(s, s)


@dataclass(frozen=True)
class ChainlinkRound:
    """One ``latestRoundData()`` result, decoded.

    All five fields preserved so callers wanting deeper round-history
    analysis (round-id continuity, ``answeredInRound`` mismatch) have
    them. The convenience :meth:`is_stale` helper covers the common
    "is the feed fresh enough?" question.
    """

    round_id: int
    answer: int  # int256, scaled by feed decimals
    started_at: int  # unix seconds
    updated_at: int  # unix seconds
    answered_in_round: int

    def is_stale(self, max_age_s: int = DEFAULT_MAX_AGE_S, *, now: float | None = None) -> bool:
        """Return ``True`` if ``updated_at`` is older than ``max_age_s`` seconds.

        ``now`` is injectable for deterministic tests; defaults to
        :func:`time.time`. A round that reports ``updated_at == 0``
        (some feeds do this on boot) is treated as stale unconditionally.
        """
        if self.updated_at <= 0:
            return True
        current = float(now) if now is not None else time.time()
        return (current - float(self.updated_at)) > float(max_age_s)


class ChainlinkAggregator(TypedContract):
    """Read-only typed wrapper for one Chainlink ``AggregatorV3Interface`` feed.

    Construction is cheap — pass in any ``_ChainCallable``-shaped client
    (the same shape ``GmxV2Arbitrum`` and ``AaveV3Arbitrum`` accept) and
    a feed address. The ``decimals()`` value is cached after the first
    read since it's immutable per feed contract.
    """

    def __init__(self, client: _ChainCallable, address: str) -> None:
        super().__init__(client, address, load_pinned_abi("chainlink/aggregator_v3.json"))
        self._decimals_cache: int | None = None

    async def decimals(self) -> int:
        """Return feed decimals (Chainlink USD feeds on Arbitrum are 8)."""
        if self._decimals_cache is not None:
            return self._decimals_cache
        raw = await self.call("decimals")
        self._decimals_cache = int(raw)
        return self._decimals_cache

    async def description(self) -> str:
        """Return the human-readable feed description, e.g. ``"BTC / USD"``."""
        return str(await self.call("description"))

    async def latest_round_data(self) -> ChainlinkRound:
        """Decode ``latestRoundData()`` into a typed :class:`ChainlinkRound`."""
        raw = await self.call("latestRoundData")
        if not isinstance(raw, tuple) or len(raw) < 5:
            raise ValueError(f"unexpected latestRoundData shape: {type(raw).__name__}: {raw!r}")
        return ChainlinkRound(
            round_id=int(raw[0]),
            answer=int(raw[1]),
            started_at=int(raw[2]),
            updated_at=int(raw[3]),
            answered_in_round=int(raw[4]),
        )

    async def latest_price(self) -> Decimal:
        """Convenience: USD price as :class:`~decimal.Decimal`, decimals applied.

        Raises ``ValueError`` if the feed reports a non-positive answer
        (Chainlink USD feeds should never go below ~$0.0001 — a zero
        or negative answer is a broken-feed signal). Callers wanting
        the staleness flag should call :meth:`latest_round_data`
        directly and inspect :meth:`ChainlinkRound.is_stale`.
        """
        round_data = await self.latest_round_data()
        if round_data.answer <= 0:
            raise ValueError(
                f"Chainlink feed {self.address} returned non-positive answer: {round_data.answer}"
            )
        decimals = await self.decimals()
        return Decimal(round_data.answer) / (Decimal(10) ** decimals)


@dataclass(frozen=True)
class ChainlinkPrice:
    """A single Chainlink price read with staleness flag.

    ``stale`` is the policy-level signal — Sentinel / chain-health gate
    can choose to downweight or refuse a stale reading rather than
    silently letting it through.
    """

    symbol: str
    feed_address: str
    usd: Decimal
    updated_at: int
    stale: bool


class ChainlinkRegistry:
    """Map token symbols → ``ChainlinkAggregator`` instances on Arbitrum One.

    Construction is cheap — feed instances are built lazily on first
    ``oracle_for()`` lookup. The default registry covers BTC, ETH, SOL,
    AVAX, DOGE, LINK; callers can add more via :meth:`register_feed`
    (e.g. for a future PEPE / SHIB / TRUMP feed without bumping the
    ``ARBITRUM_FEEDS`` dict mid-release).

    Symbol resolution always normalizes through
    :data:`WRAPPED_TO_UNDERLYING` so callers can pass in either
    ``"BTC"`` (the underlying) or ``"WBTC"`` (the wrapped token GMX
    actually uses as ``index_token``) and get the same feed.
    """

    def __init__(
        self,
        client: _ChainCallable,
        feeds: dict[str, str] | None = None,
        *,
        max_age_s: int = DEFAULT_MAX_AGE_S,
    ) -> None:
        self._client = client
        # Defensive copy + uppercase keys — symbol resolution is case-insensitive.
        merged = {k.upper(): v for k, v in ARBITRUM_FEEDS.items()}
        if feeds:
            for k, v in feeds.items():
                merged[k.upper()] = v
        self._feeds = merged
        self._instances: dict[str, ChainlinkAggregator] = {}
        self.max_age_s = int(max_age_s)

    def known_symbols(self) -> list[str]:
        """Return the list of symbols this registry can resolve, sorted."""
        return sorted(self._feeds)

    def feed_address(self, symbol: str) -> str | None:
        """Return the raw feed address for ``symbol`` (or ``None``)."""
        return self._feeds.get(_normalize_symbol(symbol))

    def register_feed(self, symbol: str, address: str) -> None:
        """Add or override a feed at runtime.

        Useful when the registry adds a new market and we don't want to
        bump the hard-coded :data:`ARBITRUM_FEEDS` until a release.
        """
        if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
            raise ValueError(f"invalid feed address: {address!r}")
        norm = _normalize_symbol(symbol)
        self._feeds[norm] = address
        # Drop cached instance — caller may have changed the address.
        self._instances.pop(norm, None)

    def oracle_for(self, symbol: str) -> ChainlinkAggregator | None:
        """Return a typed :class:`ChainlinkAggregator` for ``symbol`` (or ``None``).

        Lazily caches per-symbol instances so repeated lookups don't
        re-construct the wrapper. Returns ``None`` for unknown symbols
        (caller decides whether that's an error or a fall-through).
        """
        norm = _normalize_symbol(symbol)
        if norm not in self._feeds:
            return None
        cached = self._instances.get(norm)
        if cached is not None:
            return cached
        agg = ChainlinkAggregator(self._client, self._feeds[norm])
        self._instances[norm] = agg
        return agg

    async def fetch_price(self, symbol: str, *, now: float | None = None) -> ChainlinkPrice:
        """Fetch a typed :class:`ChainlinkPrice` (USD + staleness flag) for ``symbol``.

        Raises ``LookupError`` if the symbol isn't in the registry —
        callers wanting a soft-fail should pre-check
        :meth:`oracle_for` themselves. Raises ``ValueError`` from the
        underlying ``latest_price()`` if the feed answers non-positive.
        """
        agg = self.oracle_for(symbol)
        if agg is None:
            raise LookupError(f"no Chainlink feed registered for symbol {symbol!r}")
        round_data = await agg.latest_round_data()
        if round_data.answer <= 0:
            raise ValueError(
                f"Chainlink feed {agg.address} (symbol={symbol!r}) "
                f"returned non-positive answer: {round_data.answer}"
            )
        decimals = await agg.decimals()
        usd = Decimal(round_data.answer) / (Decimal(10) ** decimals)
        return ChainlinkPrice(
            symbol=_normalize_symbol(symbol),
            feed_address=agg.address,
            usd=usd,
            updated_at=round_data.updated_at,
            stale=round_data.is_stale(self.max_age_s, now=now),
        )

    async def verify_addresses(self) -> dict[str, bool]:
        """Probe every registered feed via ``eth_getCode``; return ``{symbol: has_code}``.

        Used by the gated integration test + the registry-bringup
        script to flag feeds whose addresses don't actually contain
        deployed bytecode (typo, wrong-chain copy-paste, deprecated
        feed). Pure RPC; no decoding.
        """
        out: dict[str, bool] = {}
        for symbol, address in self._feeds.items():
            try:
                code = await self._client._call("eth_getCode", [address, "latest"])
            except Exception:  # noqa: BLE001 — verify is best-effort
                out[symbol] = False
                continue
            # Empty bytecode is "0x" or "0x0"; anything longer means deployed.
            out[symbol] = isinstance(code, str) and len(code) > 4
        return out


__all__ = (
    "ChainlinkAggregator",
    "ChainlinkPrice",
    "ChainlinkRegistry",
    "ChainlinkRound",
    "ARBITRUM_FEEDS",
    "WRAPPED_TO_UNDERLYING",
    "DEFAULT_MAX_AGE_S",
)
