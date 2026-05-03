"""Kumbaya (MegaETH) typed read wrapper.

Kumbaya is a UniswapV3-fork DEX-spot venue, $74.8M TVL on chain 4326
(second-largest after Aave V3). Same ABI surface as canonical UniV3:
``UniswapV3Factory``, ``QuoterV2``, ``UniswapV3Pool``, ``SwapRouter02``.

Wave B step 1 scope: **read only.** Quoting, pool state, factory lookup.
Write paths (``exactInputSingle`` etc.) live in Wave C and route through
``plugins/claw-sapphire/tools/internal/megaeth_executor.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any

from ..abis.fetcher import load_pinned_abi
from ..registry import ProtocolEntry
from .base import TypedContract, _MegaETHCallable

# UniV3 fee tiers (in pips, where 1 pip = 0.0001%).
# Stable pairs: 100 (0.01%) and 500 (0.05%).
# Standard pairs: 3000 (0.3%).
# Exotic pairs: 10000 (1%).
KNOWN_FEE_TIERS: tuple[int, ...] = (100, 500, 3000, 10000)

# We compute Decimal prices from large sqrt_price_x96 values; bump the
# precision to avoid scientific-notation rounding in user-facing output.
# 60 decimal digits is comfortable for any UniV3 price up to ~10^18 / 10^-18.
# This MUST run before any large Decimal arithmetic at import time.
getcontext().prec = max(getcontext().prec, 60)

# Q96 fixed-point divisor for sqrtPriceX96 → price conversion.
# Built from the int form so the value is exact regardless of the
# Decimal context's precision at import time.
Q96 = Decimal(2**96)

#: Sentinel address returned by ``Factory.getPool`` when no pool exists.
ZERO_ADDRESS = "0x" + "0" * 40


@dataclass(frozen=True)
class KumbayaAddresses:
    """Address bundle for the Kumbaya deployment on MegaETH."""

    factory: str
    quoter_v2: str
    swap_router: str

    @classmethod
    def from_registry_entry(cls, entry: ProtocolEntry) -> KumbayaAddresses:
        return cls(
            factory=entry.address("factory"),
            quoter_v2=entry.address("quoter_v2"),
            swap_router=entry.address("swap_router"),
        )


@dataclass(frozen=True)
class QuoteResult:
    """Output of ``QuoterV2.quoteExactInputSingle`` / ``quoteExactInput``.

    ``amount_out`` is in raw output-token units (caller divides by
    ``10**decimals`` for human display).
    ``sqrt_price_x96_after`` is the post-swap sqrt price as a Q96 fixed
    point uint160.
    ``initialized_ticks_crossed`` is the number of initialized ticks the
    swap would step through — useful for slippage / route-quality
    heuristics.
    ``gas_estimate`` is the QuoterV2's reported gas estimate for the
    actual swap (note: QuoterV2's estimate is conservative and tends to
    over-report by ~10-20% vs. the live swap).
    """

    amount_out: int
    sqrt_price_x96_after: int
    initialized_ticks_crossed: int
    gas_estimate: int


@dataclass(frozen=True)
class PoolState:
    """Snapshot from ``UniswapV3Pool.slot0`` + ``liquidity`` + ``fee``.

    ``sqrt_price_x96`` is the current Q96 sqrt price.
    ``tick`` is the current tick index (int24, can be negative).
    ``liquidity`` is the active in-range liquidity (uint128).
    ``fee_pips`` is the fee in pips (3000 == 0.3%).
    ``unlocked`` is False during a swap callback — should be True for
    every external read.
    """

    sqrt_price_x96: int
    tick: int
    observation_index: int
    observation_cardinality: int
    fee_protocol: int
    unlocked: bool
    liquidity: int
    fee_pips: int

    def price_token1_per_token0(self) -> Decimal:
        """Return the spot price as ``Decimal`` (token1 per 1 token0).

        ``price = (sqrt_price_x96 / 2**96) ** 2``. This is the *raw* price
        in token-unit ratios — to get the human price (e.g. USDM per ETH)
        the caller must adjust by token-decimal scales:
        ``human = raw * 10**(decimals_token0 - decimals_token1)``.
        Returning the raw form keeps this dataclass token-agnostic.
        """
        if self.sqrt_price_x96 <= 0:
            return Decimal(0)
        sqrt_price = Decimal(self.sqrt_price_x96) / Q96
        return sqrt_price * sqrt_price


@dataclass(frozen=True)
class PoolInfo:
    """Lightweight pool descriptor used by ``top_pools_by_tvl``.

    ``pool`` is the contract address. ``token0``/``token1`` are the pair
    (sorted by address — UniV3 invariant). ``fee_pips`` is the fee tier.
    ``liquidity`` is the active in-range liquidity (uint128). ``tick`` is
    the current tick. The ``label`` is a human-readable like ``"WETH/USDM 0.3%"``.
    """

    pool: str
    token0: str
    token1: str
    fee_pips: int
    liquidity: int
    tick: int
    label: str = ""
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_lower_addr(addr: Any) -> str:
    if isinstance(addr, bytes):
        return "0x" + addr.hex()
    if isinstance(addr, str):
        return addr.lower()
    return str(addr)


def _validate_address(addr: str, *, label: str) -> str:
    if not isinstance(addr, str) or not addr.startswith("0x") or len(addr) != 42:
        raise ValueError(f"invalid {label} address: {addr!r}")
    return addr


def _validate_fee(fee: int) -> int:
    if not isinstance(fee, int) or fee < 0 or fee > 1_000_000:
        raise ValueError(f"invalid fee tier: {fee!r} (expected uint24, in pips)")
    return fee


def encode_path(path: list[tuple[str, int] | str]) -> bytes:
    """Encode a UniV3 multi-hop path: ``token0 || fee0 || token1 || fee1 || ... || tokenN``.

    ``path`` is a flat list alternating ``str`` (token address) and
    ``int`` (fee), or — for callers that prefer it — a list of
    ``(token, fee)`` tuples followed by a final token. The function
    accepts either shape::

        encode_path([WETH, 3000, USDM, 500, USDT0])
        encode_path([(WETH, 3000), (USDM, 500), USDT0])

    UniV3 path encoding: each token is 20 bytes (no 0x), each fee is 3
    bytes (uint24 BE). Length must be ``20 + N * (20 + 3)`` for
    N hops where N >= 1.
    """
    if not path:
        raise ValueError("path must contain at least one token")

    # Normalize the (token, fee) tuple form to flat.
    flat: list[Any] = []
    for item in path:
        if isinstance(item, tuple):
            if len(item) != 2:
                raise ValueError(f"path tuple must be (token, fee), got {item!r}")
            flat.extend(item)
        else:
            flat.append(item)

    if len(flat) % 2 == 0:
        raise ValueError(
            f"encoded path must alternate token/fee/token/...token (odd-count list), got {len(flat)} items"
        )

    parts: list[bytes] = []
    for i, item in enumerate(flat):
        if i % 2 == 0:
            # Token address.
            addr = _validate_address(item, label="path token")
            parts.append(bytes.fromhex(addr[2:]))
        else:
            fee = _validate_fee(item)
            parts.append(fee.to_bytes(3, "big"))
    return b"".join(parts)


# ---------------------------------------------------------------------------
# Kumbaya facade
# ---------------------------------------------------------------------------


class Kumbaya:
    """Read-only typed wrapper around the Kumbaya deployment on MegaETH.

    Constructed with a ``MegaETHClient``-shaped object and a bundle of
    addresses from the registry::

        client = MegaETHClient()
        async with client:
            kb = Kumbaya(client, KumbayaAddresses.from_registry_entry(entry))
            quote = await kb.quote_exact_input_single(WETH, USDM, fee=3000, amount_in=10**18)

    All methods are async. Pool wrappers (``pool_state``, ``ticks``)
    bind a fresh :class:`TypedContract` per pool address — there's one
    Pool ABI used by every CREATE2 pool clone, so the per-call binding
    cost is just an in-memory dict construction.
    """

    def __init__(self, client: _MegaETHCallable, addresses: KumbayaAddresses) -> None:
        self._client = client
        self.addresses = addresses

        self._factory = TypedContract(
            client,
            addresses.factory,
            load_pinned_abi("kumbaya/factory.json"),
        )
        self._quoter = TypedContract(
            client,
            addresses.quoter_v2,
            load_pinned_abi("kumbaya/quoter_v2.json"),
        )
        # SwapRouter02 ABI is bound for Wave C's write path — pinned now so
        # tests can verify the artifact is on disk and parses, but no
        # method is invoked from this read-only wrapper.
        self._swap_router = TypedContract(
            client,
            addresses.swap_router,
            load_pinned_abi("kumbaya/swap_router.json"),
        )
        # Pool ABI is reused for every pool address — load once.
        self._pool_abi = load_pinned_abi("kumbaya/pool.json")

    # ---- factory ---------------------------------------------------------

    async def get_pool(self, token_a: str, token_b: str, fee: int) -> str:
        """Return the pool address for ``(token_a, token_b, fee)``.

        UniV3's factory canonicalizes the pair internally (sorts the two
        tokens by address before hashing), so we can pass them in any
        order. Returns :data:`ZERO_ADDRESS` if no pool exists for the
        requested ``(pair, fee)`` combination.
        """
        _validate_address(token_a, label="token_a")
        _validate_address(token_b, label="token_b")
        _validate_fee(fee)
        raw = await self._factory.call("getPool", token_a, token_b, fee)
        return _to_lower_addr(raw)

    # ---- quoter ----------------------------------------------------------
    #
    # FOOTGUN — QuoterV2 is **stateMutability: nonpayable**, NOT view.
    #
    # The classic UniV3 Quoter (V1) implemented quoting by initiating a
    # *real* swap inside a try/catch, then reverting in the swap-callback
    # with the result encoded in revert data — callers had to parse the
    # error bytes. QuoterV2 keeps the "real swap inside try/catch" trick
    # but catches the revert *internally* and returns the values via
    # standard returndata. So QuoterV2 IS callable via ``eth_call``
    # (which is what we do here, since our TypedContract issues
    # ``eth_call`` for every method); but it is NOT callable via
    # ``staticcall`` from another contract, because the function still
    # technically writes (and the EVM allows the write through inside
    # the simulated swap, only reverting at the end).
    #
    # Practical takeaway: ``await kb.quote_exact_input_single(...)`` works.
    # On-chain integrators must use a regular CALL, not STATICCALL.

    async def quote_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        amount_in: int,
        sqrt_price_limit_x96: int = 0,
    ) -> QuoteResult:
        """Quote a single-hop swap. Returns :class:`QuoteResult`.

        ``amount_in`` is in raw input-token units. ``sqrt_price_limit_x96=0``
        disables the limit (default; quote against current pool price).
        """
        _validate_address(token_in, label="token_in")
        _validate_address(token_out, label="token_out")
        _validate_fee(fee)
        if not isinstance(amount_in, int) or amount_in < 0:
            raise ValueError(f"amount_in must be non-negative int, got {amount_in!r}")
        if not isinstance(sqrt_price_limit_x96, int) or sqrt_price_limit_x96 < 0:
            raise ValueError(
                f"sqrt_price_limit_x96 must be non-negative int, got {sqrt_price_limit_x96!r}"
            )

        params = (token_in, token_out, amount_in, fee, sqrt_price_limit_x96)
        raw = await self._quoter.call("quoteExactInputSingle", params)
        # Returns (amountOut, sqrtPriceX96After, initializedTicksCrossed, gasEstimate)
        amount_out, sqrt_after, ticks_crossed, gas = raw
        return QuoteResult(
            amount_out=int(amount_out),
            sqrt_price_x96_after=int(sqrt_after),
            initialized_ticks_crossed=int(ticks_crossed),
            gas_estimate=int(gas),
        )

    async def quote_exact_input(
        self,
        path: bytes | list[Any],
        amount_in: int,
    ) -> QuoteResult:
        """Quote a multi-hop swap.

        ``path`` may be raw encoded bytes (per UniV3 path encoding) or a
        list accepted by :func:`encode_path`. ``amount_in`` is raw input
        units.

        Returns :class:`QuoteResult`. Note: QuoterV2's
        ``quoteExactInput`` signature is
        ``(bytes path, uint256 amountIn) -> (uint256 amountOut, uint160[] sqrtPricesX96After, uint32[] initializedTicksCrossedList, uint256 gasEstimate)``,
        so ``sqrt_price_x96_after`` and ``initialized_ticks_crossed`` are
        the **last hop's** values for symmetry with the single-hop
        return shape. Full per-hop arrays live in the ``raw`` field on a
        future caller — for Wave B step 1 we keep the single-hop shape
        and document this here.
        """
        if isinstance(path, list):
            encoded = encode_path(path)
        elif isinstance(path, (bytes, bytearray)):
            encoded = bytes(path)
        else:
            raise TypeError(f"path must be bytes or list, got {type(path).__name__}")

        if not isinstance(amount_in, int) or amount_in < 0:
            raise ValueError(f"amount_in must be non-negative int, got {amount_in!r}")
        # Path validation: 20 + N * 23 bytes for N >= 1.
        if len(encoded) < 43 or (len(encoded) - 20) % 23 != 0:
            raise ValueError(
                f"invalid encoded path length {len(encoded)}: expected 20 + N*23 for N>=1"
            )

        raw = await self._quoter.call("quoteExactInput", encoded, amount_in)
        # Returns (amountOut, sqrtPricesX96After[], initializedTicksCrossedList[], gasEstimate).
        amount_out, sqrt_list, ticks_list, gas = raw
        last_sqrt = int(sqrt_list[-1]) if sqrt_list else 0
        last_ticks = int(ticks_list[-1]) if ticks_list else 0
        return QuoteResult(
            amount_out=int(amount_out),
            sqrt_price_x96_after=last_sqrt,
            initialized_ticks_crossed=last_ticks,
            gas_estimate=int(gas),
        )

    # ---- pool reads ------------------------------------------------------

    def _bind_pool(self, pool: str) -> TypedContract:
        _validate_address(pool, label="pool")
        return TypedContract(self._client, pool, self._pool_abi)

    async def pool_state(self, pool: str) -> PoolState:
        """Fetch ``slot0 + liquidity + fee`` for an existing pool.

        Three sequential ``eth_call`` requests; could be batched once
        Multicall3 is wired into ``base.py``. For Wave B step 1 the
        sequential pattern matches Wave A's use-case and keeps the
        wrapper simple.
        """
        c = self._bind_pool(pool)
        slot0 = await c.call("slot0")
        liquidity = await c.call("liquidity")
        fee = await c.call("fee")
        # slot0 returns 7 values.
        (
            sqrt_price_x96,
            tick,
            obs_idx,
            obs_card,
            _obs_card_next,
            fee_protocol,
            unlocked,
        ) = slot0
        return PoolState(
            sqrt_price_x96=int(sqrt_price_x96),
            tick=int(tick),
            observation_index=int(obs_idx),
            observation_cardinality=int(obs_card),
            fee_protocol=int(fee_protocol),
            unlocked=bool(unlocked),
            liquidity=int(liquidity),
            fee_pips=int(fee),
        )

    # ---- enumeration -----------------------------------------------------

    async def top_pools_by_tvl(
        self,
        candidates: list[tuple[str, str, int, str]] | None = None,
        *,
        limit: int = 10,
    ) -> list[PoolInfo]:
        """Enumerate the top live pools by active-liquidity (rough TVL proxy).

        ``candidates`` is a list of ``(token_a, token_b, fee, label)`` tuples to
        probe via ``Factory.getPool``. We keep only those that resolve to
        a non-zero pool address AND return non-zero ``liquidity`` from
        ``UniswapV3Pool.liquidity()`` — this avoids shipping a
        marketing-copy pool list. If ``candidates`` is None, we use the
        Wave-B-known set of MegaETH stablecoin/WETH pools (manually
        cross-checked on 2026-04-30).

        UniV3's ``liquidity()`` is *active in-range* liquidity, not full
        TVL — but it's the right proxy for "tradeable depth right now",
        which is what callers care about for routing.
        """
        if candidates is None:
            candidates = list(_DEFAULT_POOL_CANDIDATES)

        out: list[PoolInfo] = []
        for token_a, token_b, fee, label in candidates:
            try:
                pool = await self.get_pool(token_a, token_b, fee)
            except Exception:
                continue
            if pool == ZERO_ADDRESS:
                continue
            try:
                state = await self.pool_state(pool)
            except Exception:
                continue
            if state.liquidity <= 0:
                continue
            # Sort token addrs to match UniV3's canonical ordering.
            t0, t1 = sorted([token_a.lower(), token_b.lower()])
            out.append(
                PoolInfo(
                    pool=pool,
                    token0=t0,
                    token1=t1,
                    fee_pips=fee,
                    liquidity=state.liquidity,
                    tick=state.tick,
                    label=label,
                )
            )

        # Sort by liquidity desc as a coarse TVL proxy.
        out.sort(key=lambda p: -p.liquidity)
        return out[:limit]


# Verified-live candidate set — every pair below was probed via factory
# `getPool` against mainnet on 2026-04-30 and confirmed to have a
# non-zero pool address. Liquidity is checked at call-time, so empty
# pools get filtered automatically.
_DEFAULT_POOL_CANDIDATES: tuple[tuple[str, str, int, str], ...] = (
    # WETH/USDM family
    (
        "0x4200000000000000000000000000000000000006",
        "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
        500,
        "WETH/USDM 0.05%",
    ),
    (
        "0x4200000000000000000000000000000000000006",
        "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
        3000,
        "WETH/USDM 0.3%",
    ),
    (
        "0x4200000000000000000000000000000000000006",
        "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
        100,
        "WETH/USDM 0.01%",
    ),
    # WETH/USDT0 family
    (
        "0x4200000000000000000000000000000000000006",
        "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
        500,
        "WETH/USDT0 0.05%",
    ),
    (
        "0x4200000000000000000000000000000000000006",
        "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
        3000,
        "WETH/USDT0 0.3%",
    ),
    (
        "0x4200000000000000000000000000000000000006",
        "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
        100,
        "WETH/USDT0 0.01%",
    ),
    # USDM/USDT0 stable family
    (
        "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
        "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
        100,
        "USDM/USDT0 0.01%",
    ),
    (
        "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
        "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
        500,
        "USDM/USDT0 0.05%",
    ),
    # USDM/USDe and USDT0/USDe
    (
        "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
        "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34",
        100,
        "USDM/USDe 0.01%",
    ),
    (
        "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
        "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34",
        100,
        "USDT0/USDe 0.01%",
    ),
    (
        "0x4200000000000000000000000000000000000006",
        "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34",
        3000,
        "WETH/USDe 0.3%",
    ),
)


def sqrt_price_x96_to_price(
    sqrt_price_x96: int,
    *,
    decimals_token0: int,
    decimals_token1: int,
) -> Decimal:
    """Convert sqrtPriceX96 to a human-readable token1-per-token0 price.

    ``raw_price = (sqrt_price_x96 / 2**96) ** 2``
    ``human = raw_price * 10**(decimals_token0 - decimals_token1)``

    Example: WETH (18) / USDM (18) pool with sqrt_price_x96 = 3.77e30,
    raw_price ≈ 2256, decimal-adjustment is 0 → human price ≈ 2256 USDM/WETH.

    For a USDM/USDT0 pool where USDM=18 and USDT0=6, decimal-adjust =
    18 - 6 = 12, which scales the raw price up by 1e12 (since USDT0 has
    fewer decimals, you get more "USDT0 raw" per 1 "USDM raw").
    """
    if sqrt_price_x96 <= 0:
        return Decimal(0)
    sqrt_price = Decimal(sqrt_price_x96) / Q96
    raw = sqrt_price * sqrt_price
    adj = Decimal(10) ** Decimal(decimals_token0 - decimals_token1)
    return raw * adj


def tick_to_price(
    tick: int,
    *,
    decimals_token0: int,
    decimals_token1: int,
) -> Decimal:
    """Convert a UniV3 tick index to a human-readable token1/token0 price.

    Useful when callers have only the tick and need the price (e.g.
    when serializing pool state to JSON). Math: ``price = 1.0001 ** tick``,
    decimal-adjusted the same as :func:`sqrt_price_x96_to_price`.
    """
    raw = Decimal(math.pow(1.0001, tick))
    adj = Decimal(10) ** Decimal(decimals_token0 - decimals_token1)
    return raw * adj
