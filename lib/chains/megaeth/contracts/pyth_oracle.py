"""Pyth Network oracle wrapper + canonical MegaETH price-id registry.

Wave B.3 follow-up. Pairs with :mod:`gmx_price_adapter` to give GMX V2
markets a price source for tokens that aren't in the Aave V3 oracle.

Why this exists
===============

The MegaETH GMX V2 deployment lists ~6 perps markets (BTC/USD, ETH/USD,
SOL/USD, plus a couple of synth indices). The Aave V3 oracle on MegaETH
covers the lending venue's reserves — at the time of writing, that's
USDM + USDT0 + a handful of LSTs. The intersection between Aave-priced
tokens and GMX-traded indices is essentially empty: every GMX market
on MegaETH ends up with ``state="unpriced"`` from the Aave-only path.

Pyth solves this. Pyth has live BTC/USD, ETH/USD, SOL/USD, USDC/USD,
and USDT/USD feeds on MegaETH (and across every other EVM chain Pyth
supports — same contract address by CREATE2). With Pyth as the
fallback, every GMX market on MegaETH becomes priceable, and we can
query live funding-rate APRs that were previously locked behind a
hard-coded ``-75%`` placeholder.

Why this is its own module
==========================

Pyth reads are pure read-only HTTP RPC against a single contract
(``0x2880aB155794e7179c9eE2e38200202908C17B43`` on MegaETH). The
shape is fundamentally different from Chainlink's per-asset proxy
contracts — Pyth uses **one contract** with per-asset ``bytes32
priceId`` arguments. That justifies a dedicated wrapper rather than
reusing the Chainlink registry pattern as-is.

The :class:`GmxPriceAdapter` composes this in as a fallback rather
than owning the Pyth read logic itself, so a future Pendle / Synthetix
adapter on MegaETH can reuse the same registry.

Staleness gating
================

Pyth feeds publish on a sub-second cadence on the off-chain side, but
the on-chain ``getPriceUnsafe`` call returns the **last cached** price
— if no one has called ``updatePriceFeeds`` recently (which costs
gas), the on-chain reading can be stale. Wave B.3 read paths don't
ever update the feed (we don't want to burn gas), so we always call
``getPriceUnsafe`` and surface staleness via :meth:`PythPrice.is_stale`.
The default ``max_age_s`` is **3600** (1 hour) — same threshold as
Chainlink, conservative enough that even a quiet feed will trigger
staleness only when the keeper is genuinely broken. Sentinel can
downweight or refuse stale readings at policy level.

Decimals discipline
===================

Pyth USD prices are returned as ``(int64 price, int32 expo)`` where
``USD = price * 10**expo``. For majors, ``expo`` is typically ``-8``
(so $76,774.81 BTC comes back as ``price=7677481000000``,
``expo=-8``). Callers wanting to plug a Pyth price into GMX's
``Price.Props`` shape (1e30-scaled by ``10**(30 - tokenDecimals)``)
should use :func:`encode_gmx_price` from ``gmx_v2.py`` against the
*token decimals*, not the Pyth ``expo``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..abis.fetcher import load_pinned_abi
from .base import TypedContract, _MegaETHCallable


#: Default staleness threshold for Pyth feed reads (seconds).
#:
#: Pyth publishes off-chain at sub-second cadence, but the on-chain
#: cached value only updates when a keeper (or a user paying gas)
#: calls ``updatePriceFeeds``. A reading older than 1h on a major
#: pair is a soft warning (markets quiet OR keeper lagging); older
#: than 24h is almost always a real failure.
DEFAULT_MAX_AGE_S = 3600  # 1 hour


#: Single Pyth contract address on MegaETH (mainnet AND testnet —
#: Pyth uses CREATE2 to keep address parity across all EVM chains).
#: Reference: https://docs.pyth.network/price-feeds/contract-addresses/evm
MEGAETH_PYTH_ADDRESS = "0x2880aB155794e7179c9eE2e38200202908C17B43"


#: Canonical Pyth price-feed IDs (bytes32, hex with 0x prefix).
#:
#: Source: https://www.pyth.network/developers/price-feed-ids
#: These are the same on every chain Pyth supports — they identify
#: the off-chain price feed, not a per-chain deployment. Symbol
#: convention is the *underlying asset* (BTC, ETH, SOL); wrapped
#: tokens map through :data:`WRAPPED_TO_UNDERLYING`.
MEGAETH_PRICE_IDS: dict[str, str] = {
    "BTC": "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "ETH": "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "SOL": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "USDC": "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "USDT": "0x2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b",
}


#: Wrapped-token symbol → underlying-asset symbol. GMX index tokens are
#: usually the wrapped ERC-20 (WBTC, WETH) but Pyth feeds key off the
#: underlying. Mirrors the Chainlink-on-Arbitrum mapping.
WRAPPED_TO_UNDERLYING: dict[str, str] = {
    "WBTC": "BTC",
    "BTCB": "BTC",
    "WETH": "ETH",
    "WSOL": "SOL",
    # USDC/USDT pass through directly — included here for symmetry only.
    "USDC.E": "USDC",
    "USDT0": "USDT",
}


def _normalize_symbol(symbol: str) -> str:
    """Uppercase + strip a token symbol; resolve wrapped→underlying."""
    s = (symbol or "").strip().upper()
    return WRAPPED_TO_UNDERLYING.get(s, s)


def _normalize_price_id(price_id: str | bytes) -> bytes:
    """Coerce a hex string or bytes priceId to canonical 32-byte form.

    Accepts ``"0x..."``, ``"..."`` (no prefix), or raw bytes. Raises
    ``ValueError`` if the result isn't exactly 32 bytes — Pyth priceIds
    are always 32 bytes (one keccak256-style hash per feed).
    """
    if isinstance(price_id, bytes):
        raw = price_id
    elif isinstance(price_id, str):
        s = price_id.strip()
        if s.startswith(("0x", "0X")):
            s = s[2:]
        if len(s) != 64:
            raise ValueError(
                f"invalid Pyth priceId hex length: expected 64 hex chars, got {len(s)} "
                f"(input={price_id!r})"
            )
        try:
            raw = bytes.fromhex(s)
        except ValueError as exc:
            raise ValueError(f"invalid Pyth priceId hex: {price_id!r}") from exc
    else:
        raise TypeError(f"priceId must be str or bytes, got {type(price_id).__name__}")
    if len(raw) != 32:
        raise ValueError(f"Pyth priceId must be 32 bytes, got {len(raw)}")
    return raw


@dataclass(frozen=True)
class PythPrice:
    """One ``getPriceUnsafe()`` result, decoded.

    All four fields preserved so callers wanting deeper analysis
    (confidence intervals, publish-time skew) have them. The
    convenience helpers cover the common questions.
    """

    price: int  # int64, scaled by 10**expo
    conf: int  # uint64, confidence interval scaled by 10**expo
    expo: int  # int32, typically negative (e.g. -8 for USD majors)
    publish_time: int  # unix seconds — when the off-chain feed last published

    def is_stale(self, max_age_s: int = DEFAULT_MAX_AGE_S, *, now: float | None = None) -> bool:
        """Return ``True`` if ``publish_time`` is older than ``max_age_s`` seconds.

        ``now`` is injectable for deterministic tests; defaults to
        :func:`time.time`. A reading that reports ``publish_time == 0``
        (cold contract, never updated) is treated as stale unconditionally.
        """
        if self.publish_time <= 0:
            return True
        current = float(now) if now is not None else time.time()
        return (current - float(self.publish_time)) > float(max_age_s)

    def as_decimal_usd(self) -> Decimal:
        """Convert to a USD-denominated :class:`~decimal.Decimal`.

        Pyth USD prices have ``expo`` typically in [-12, -2]; we apply
        ``price * 10**expo`` exactly via :class:`Decimal` to preserve
        precision. A non-positive ``price`` raises ``ValueError`` —
        Pyth USD feeds should never report zero or negative.
        """
        if self.price <= 0:
            raise ValueError(f"Pyth price must be > 0, got {self.price}")
        # expo is signed; Decimal handles both positive and negative powers.
        if self.expo >= 0:
            return Decimal(self.price) * (Decimal(10) ** self.expo)
        return Decimal(self.price) / (Decimal(10) ** (-self.expo))

    def confidence_pct(self) -> Decimal:
        """Return the Pyth confidence interval as a fraction of price.

        E.g. a Pyth read with ``price=7677481000000`` and
        ``conf=1000000`` has confidence ≈ 0.013% of price (a tight
        feed). Sentinel can downweight signals where the confidence
        widens beyond a threshold (typically >0.5% on majors).
        """
        if self.price <= 0:
            return Decimal(0)
        return Decimal(self.conf) / Decimal(self.price)


class PythAggregator(TypedContract):
    """Read-only typed wrapper for the single MegaETH Pyth contract.

    Construction is cheap — pass in any ``_MegaETHCallable``-shaped
    client (the same shape ``GmxV2`` and ``AaveV3`` accept) and an
    address (defaults to :data:`MEGAETH_PYTH_ADDRESS`). Per-asset
    feeds are addressed by ``priceId`` at call time, not by per-feed
    instantiation — this is the structural difference vs Chainlink.
    """

    def __init__(self, client: _MegaETHCallable, address: str = MEGAETH_PYTH_ADDRESS) -> None:
        super().__init__(client, address, load_pinned_abi("pyth/pyth.json"))

    async def get_price_unsafe(self, price_id: str | bytes) -> PythPrice:
        """Decode ``getPriceUnsafe(bytes32 id)`` into a typed :class:`PythPrice`.

        ``price_id`` accepts hex (with or without ``0x`` prefix) or raw
        32-byte ``bytes``. The "unsafe" name is Pyth's — it just means
        no on-contract staleness check. We surface staleness explicitly
        via :meth:`PythPrice.is_stale`.

        Raises ``ValueError`` for malformed priceIds. Raises whatever
        the underlying RPC raises if the contract reverts (typically
        ``RuntimeError`` from the JSON-RPC layer when the price feed
        is unknown to the contract — Pyth reverts with ``PriceFeedNotFound``).
        """
        raw_id = _normalize_price_id(price_id)
        raw = await self.call("getPriceUnsafe", raw_id)
        # The decoded tuple shape is (price, conf, expo, publishTime).
        if not isinstance(raw, tuple) or len(raw) < 4:
            raise ValueError(f"unexpected getPriceUnsafe shape: {type(raw).__name__}: {raw!r}")
        return PythPrice(
            price=int(raw[0]),
            conf=int(raw[1]),
            expo=int(raw[2]),
            publish_time=int(raw[3]),
        )

    async def latest_price(self, price_id: str | bytes) -> Decimal:
        """Convenience: USD price as :class:`~decimal.Decimal`.

        Wraps :meth:`get_price_unsafe` and applies the ``expo`` scaling.
        Raises ``ValueError`` if the feed reports ``price <= 0`` (a
        broken-feed signal). Callers wanting the staleness flag should
        call :meth:`get_price_unsafe` directly and inspect
        :meth:`PythPrice.is_stale`.
        """
        price = await self.get_price_unsafe(price_id)
        return price.as_decimal_usd()


@dataclass(frozen=True)
class PythRegistryPrice:
    """A single Pyth price read with staleness flag (registry-level).

    Mirrors the ``ChainlinkPrice`` shape so callers that already
    consume the Chainlink-on-Arbitrum result can swap in the Pyth
    flavor with no shape changes.
    """

    symbol: str
    price_id: str
    usd: Decimal
    publish_time: int
    stale: bool


class PythRegistry:
    """Map token symbols → Pyth ``priceId`` lookups on MegaETH.

    Construction is cheap — the single :class:`PythAggregator` instance
    is built lazily on first use. The default registry covers BTC, ETH,
    SOL, USDC, USDT (the practical universe for GMX V2 markets on
    MegaETH at the time of writing). Callers can add more via
    :meth:`register_price_id` (e.g. for a future PEPE / SHIB / TRUMP
    feed without bumping the hard-coded :data:`MEGAETH_PRICE_IDS`).

    Symbol resolution always normalizes through
    :data:`WRAPPED_TO_UNDERLYING` so callers can pass in either
    ``"BTC"`` (the underlying) or ``"WBTC"`` (the wrapped token GMX
    actually uses as ``index_token``) and get the same priceId.
    """

    def __init__(
        self,
        client: _MegaETHCallable,
        price_ids: dict[str, str] | None = None,
        *,
        address: str = MEGAETH_PYTH_ADDRESS,
        max_age_s: int = DEFAULT_MAX_AGE_S,
    ) -> None:
        self._client = client
        self._address = address
        merged = {k.upper(): v for k, v in MEGAETH_PRICE_IDS.items()}
        if price_ids:
            for k, v in price_ids.items():
                merged[k.upper()] = v
        # Validate every priceId at construction — fail fast on a typo.
        for sym, pid in merged.items():
            _normalize_price_id(pid)
        self._price_ids = merged
        self._aggregator: PythAggregator | None = None
        self.max_age_s = int(max_age_s)

    def known_symbols(self) -> list[str]:
        """Return the list of symbols this registry can resolve, sorted."""
        return sorted(self._price_ids)

    def price_id(self, symbol: str) -> str | None:
        """Return the raw priceId hex for ``symbol`` (or ``None``)."""
        return self._price_ids.get(_normalize_symbol(symbol))

    def register_price_id(self, symbol: str, price_id: str) -> None:
        """Add or override a priceId at runtime.

        Useful when the registry adds a new market and we don't want
        to bump the hard-coded :data:`MEGAETH_PRICE_IDS` until a
        release.
        """
        _normalize_price_id(price_id)  # validate
        norm = _normalize_symbol(symbol)
        self._price_ids[norm] = price_id

    def aggregator(self) -> PythAggregator:
        """Lazy-construct the single :class:`PythAggregator` instance."""
        if self._aggregator is None:
            self._aggregator = PythAggregator(self._client, self._address)
        return self._aggregator

    def oracle_for(
        self, symbol: str
    ) -> tuple[PythAggregator, str] | None:
        """Return ``(aggregator, priceId)`` for ``symbol`` (or ``None``).

        The 2-tuple shape mirrors how callers naturally use Pyth:
        every Pyth read needs both the contract handle AND the
        per-asset priceId. Returns ``None`` for unknown symbols
        (caller decides whether that's an error or fall-through).

        Note this differs from :meth:`ChainlinkRegistry.oracle_for`,
        which returns just the per-feed contract — Chainlink has one
        contract per feed; Pyth has one contract for all feeds. The
        2-tuple captures that asymmetry without surprising callers.
        """
        norm = _normalize_symbol(symbol)
        pid = self._price_ids.get(norm)
        if pid is None:
            return None
        return self.aggregator(), pid

    async def fetch_price(
        self, symbol: str, *, now: float | None = None
    ) -> PythRegistryPrice:
        """Fetch a typed :class:`PythRegistryPrice` (USD + staleness) for ``symbol``.

        Raises ``LookupError`` if the symbol isn't in the registry —
        callers wanting a soft-fail should pre-check :meth:`oracle_for`
        themselves. Raises ``ValueError`` from the underlying
        :meth:`PythPrice.as_decimal_usd` if the feed answers
        non-positive.
        """
        resolved = self.oracle_for(symbol)
        if resolved is None:
            raise LookupError(f"no Pyth priceId registered for symbol {symbol!r}")
        agg, pid = resolved
        price = await agg.get_price_unsafe(pid)
        usd = price.as_decimal_usd()
        return PythRegistryPrice(
            symbol=_normalize_symbol(symbol),
            price_id=pid,
            usd=usd,
            publish_time=price.publish_time,
            stale=price.is_stale(self.max_age_s, now=now),
        )

    def is_stale(
        self, price: PythPrice, max_age_s: int | None = None, *, now: float | None = None
    ) -> bool:
        """Helper: apply this registry's staleness policy to a raw read.

        Useful when a caller has already done the read via
        :meth:`PythAggregator.get_price_unsafe` and wants to apply the
        registry-default threshold without re-fetching.
        """
        threshold = max_age_s if max_age_s is not None else self.max_age_s
        return price.is_stale(threshold, now=now)

    async def verify_address(self) -> bool:
        """Probe the Pyth contract via ``eth_getCode``; return ``True`` if deployed.

        Used by the gated integration test + the registry-bringup
        script to confirm the Pyth address has bytecode on MegaETH.
        Pure RPC; no decoding.
        """
        client_call: Any = self._client
        try:
            code = await client_call._call("eth_getCode", [self._address, "latest"])
        except Exception:  # noqa: BLE001 — verify is best-effort
            return False
        return isinstance(code, str) and len(code) > 4


__all__ = (
    "PythAggregator",
    "PythPrice",
    "PythRegistry",
    "PythRegistryPrice",
    "MEGAETH_PYTH_ADDRESS",
    "MEGAETH_PRICE_IDS",
    "WRAPPED_TO_UNDERLYING",
    "DEFAULT_MAX_AGE_S",
)
