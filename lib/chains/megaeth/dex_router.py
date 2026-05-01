"""Best-quote router across registered MegaETH DEXes.

Wave B step 1 only knows Kumbaya, so this module is essentially a
thin pass-through. The abstraction matters because Wave B steps 2–4
will add USDM internal AMM, Prism, and (eventually) GMX V2 spot legs —
each one slots in by extending :class:`DexRoutingTable` with another
``(venue, quote_fn)`` entry, no surgery on the facade.

Reads only. Wave C's executor takes the same ``SwapQuote`` and turns
it into a ``SwapRouter02.exactInputSingle`` (or multi-hop) tx via the
gated ``megaeth_executor``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .contracts.kumbaya import KNOWN_FEE_TIERS, Kumbaya, QuoteResult


@dataclass(frozen=True)
class SwapQuote:
    """Best-of-DEXes quote for a token-in / token-out / amount-in.

    ``venue`` identifies the source DEX (e.g. ``"kumbaya"``).
    ``fee_pips`` is the fee tier on the routed pool(s).
    ``amount_out`` is the raw output-token units the swap would yield.
    ``effective_price_token1_per_token0`` is the realized price for the
    swap (amount_out / amount_in, decimal-adjusted to token-unit ratios
    only — caller adjusts for token decimals if displaying).
    ``hops`` is 1 for direct quotes, >1 for multi-hop routes.
    ``gas_estimate`` is the venue-reported gas estimate.
    ``raw`` carries the underlying :class:`QuoteResult` for callers that
    need ``sqrt_price_x96_after`` etc.
    """

    venue: str
    token_in: str
    token_out: str
    amount_in: int
    amount_out: int
    fee_pips: int
    hops: int
    gas_estimate: int
    raw: QuoteResult | None = field(default=None, compare=False, repr=False)

    @property
    def effective_price(self) -> Decimal:
        if self.amount_in <= 0:
            return Decimal(0)
        return Decimal(self.amount_out) / Decimal(self.amount_in)


# ---- venue quote callable shape ------------------------------------------
#
# Each registered DEX exposes a "best quote across my fee tiers / routes"
# coroutine. The router collects them all and picks the highest amount_out.
QuoteFn = Callable[[str, str, int], Awaitable[SwapQuote | None]]


async def quote_kumbaya(
    kb: Kumbaya,
    token_in: str,
    token_out: str,
    amount_in: int,
    *,
    fee_tiers: tuple[int, ...] = KNOWN_FEE_TIERS,
) -> SwapQuote | None:
    """Probe Kumbaya across all UniV3 fee tiers and return the best."""
    best: SwapQuote | None = None
    for fee in fee_tiers:
        try:
            q = await kb.quote_exact_input_single(token_in, token_out, fee, amount_in)
        except Exception:
            # No pool / pool empty / revert — try next tier.
            continue
        if q.amount_out <= 0:
            continue
        candidate = SwapQuote(
            venue="kumbaya",
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            amount_out=q.amount_out,
            fee_pips=fee,
            hops=1,
            gas_estimate=q.gas_estimate,
            raw=q,
        )
        if best is None or candidate.amount_out > best.amount_out:
            best = candidate
    return best


@dataclass
class DexRoutingTable:
    """Registry of (venue_name, quote_fn) pairs.

    Order matters only for tie-breaking: when two venues return the same
    ``amount_out`` we keep the first-registered (priority order). For
    Wave B step 1 there's only one venue.
    """

    entries: list[tuple[str, QuoteFn]] = field(default_factory=list)

    def register(self, venue: str, fn: QuoteFn) -> None:
        self.entries.append((venue, fn))

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Any:
        return iter(self.entries)


async def best_quote(
    table: DexRoutingTable,
    token_in: str,
    token_out: str,
    amount_in: int,
) -> SwapQuote | None:
    """Run every registered venue's quote_fn and return the best."""
    best: SwapQuote | None = None
    for _venue, fn in table.entries:
        try:
            q = await fn(token_in, token_out, amount_in)
        except Exception:
            continue
        if q is None:
            continue
        if best is None or q.amount_out > best.amount_out:
            best = q
    return best
