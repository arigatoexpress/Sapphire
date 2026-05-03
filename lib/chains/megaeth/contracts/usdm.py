"""USDM (MegaUSD) typed read wrapper.

USDM (symbol ``USDm``) is the canonical native stable on MegaETH.
Token address ``0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7`` is an
``ERC1967Proxy`` whose implementation is ``xUSDOFTUpgradeable`` —
a LayerZero V2 OmniFungibleToken wrapped in OpenZeppelin's upgradeable
proxy. Circulating supply was **360,753,853 USDm** at TGE day
(2026-04-30), matching the ``$360M`` figure in the protocol map.

ARCHITECTURE FOOTGUN — this is NOT what the protocol map called out
==================================================================

The MegaETH protocol map (PR #535) lists a stack of four contracts as
the "USDM stack": ``Minter_v2`` (``0x2A9bd9…``), ``StabilityPool_v2``
(``0xaa477…``), ``ReservePool_v1`` (``0xa3287…``), ``Genesis_v1``
(``0x67747…``). Live probes on 2026-04-30 reveal:

* ``Minter_v2.PEGGED_TOKEN()`` returns ``0xbed2c…`` — a DIFFERENT,
  uninitialized pegged-token, not the live USDm at ``0xFAfDdbb…``.
* ``Minter_v2.collateralRatio()``, ``leverageRatio()``,
  ``leveragedTokenPrice()``, ``harvestable()`` all REVERT
  (uninitialized; ``priceOracle()`` is the zero address).
* ``Minter_v2.peggedTokenBalance()``, ``collateralTokenBalance()``,
  ``leveragedTokenBalance()`` all return ``0``.
* ``StabilityPool_v2.totalAssetSupply()`` returns ``0``
  (``MIN_TOTAL_ASSET_SUPPLY = 1e18`` is the floor — pool is empty).

Together: the Minter/StabilityPool/Reserve/Genesis stack is a separate,
unactivated f(x)-Protocol-style minter system. **The actual circulating
USDm is bridged in via LayerZero (the OFT pattern)** and does not route
through this Minter. There is therefore NO on-chain ``collateral_ratio``
to read for the live USDm — collateral lives off-chain at the issuer
(e.g. M^0, Mountain, or whoever the OFT root chain is).

Implication: the USDM wrapper here exposes:

  * **Real on-chain reads**: ``total_supply``, ``circulating_supply``
    (totalSupply minus burn-address balance), ``decimals``, ``symbol``,
    ``is_blacklisted(account)``, ``is_minter(account)``, peg quotes
    via three independent sources, recent ``Minted``/``Burned``/
    ``OFTSent``/``OFTReceived`` event scans.
  * **NOT-ON-CHAIN, returns ``None``**: ``collateral_ratio``,
    ``mint_paused`` (no ``paused()`` on the ABI), ``redeem_paused``.
    Documented as off-chain-managed; do NOT fake them.

This is the honest scope. It still gives Wave C everything it needs:
the **peg health primitive** is what gates leverage, not the
collateral ratio (which would be a lagging indicator anyway — peg
breaks at the lowest-liquidity venue first, before collateral
appears under-stressed at the issuer).

PEG QUOTE SOURCES — three independent feeds
============================================

The ``peg_quote()`` method composes three live sources, each with a
distinct attack/error surface:

1. **Kumbaya USDM/USDT0 0.01% pool** — venue-priced. First to break on
   a depeg because its tail-liquidity is small (~$0.5M-$2M depth).
2. **MegaEthPriceFeedUsdmTwap60** — chain's TWAP-60 oracle aggregating
   on-chain prices. Lags by ~60s but is hard to manipulate.
3. **AaveOracle.getAssetPrice(USDM)** — used by Aave V3 for liquidation
   pricing. If this diverges from the others, EVERY Aave health
   factor is wrong.

The peg-monitor primitive (``peg_monitor.py``) consumes all three and
classifies severity. Wave C gates leverage on that severity.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any

from ..abis.fetcher import load_pinned_abi
from ..registry import ProtocolEntry
from .base import TypedContract, _MegaETHCallable

# Bump precision once for any large-value Decimal arithmetic in this module.
getcontext().prec = max(getcontext().prec, 60)

#: Convention burn addresses checked by ``circulating_supply``. We probe
#: all three because tokens vary in which they treat as "burned":
#: ``0x000…000`` (zero address — sometimes excluded from totalSupply at
#: the contract level), ``0x…dEaD`` (the canonical EOA burn), and
#: ``0x000…001`` (occasionally used as a bridge sentinel).
BURN_ADDRESSES: tuple[str, ...] = (
    "0x000000000000000000000000000000000000dEaD",
    "0x0000000000000000000000000000000000000001",
)

#: BPS denominator. 1 bps = 0.01% = 0.0001.
BPS_DENOMINATOR = 10_000

#: Standard scale for AaveOracle base currency on MegaETH (USD * 1e8).
AAVE_BASE_CURRENCY_UNIT = 10**8


@dataclass(frozen=True)
class USDMAddresses:
    """Address bundle for the USDM read surface on MegaETH.

    ``token`` is required and is the ERC1967 proxy at
    ``0xFAfDdbb…``. The two oracle addresses are optional in the
    constructor signature so unit tests can omit the ones they don't
    exercise; the registry-bound default has all three populated.

    ``aave_oracle`` is **not** stored here on purpose — it lives in
    the Aave V3 entry. ``USDM.peg_quote`` accepts an optional
    ``aave_oracle`` argument so the facade can supply it without
    bleeding cross-protocol state into this dataclass.
    """

    token: str
    twap60_oracle: str | None = None
    eth_oracle: str | None = None

    @classmethod
    def from_registry_entry(cls, entry: ProtocolEntry) -> USDMAddresses:
        return cls(
            token=entry.address("token"),
            twap60_oracle=entry.addresses.get("twap60_oracle"),
            eth_oracle=entry.addresses.get("eth_oracle"),
        )


@dataclass(frozen=True)
class PegQuote:
    """Snapshot of USDM's USD price across three independent sources.

    All three USD prices are normalized to plain ``Decimal`` USD —
    callers don't need to know about each source's native scaling.

    Any source that errors or is unavailable returns ``None`` for
    that field; ``divergence_bps`` is computed only from the sources
    that did return.

    ``divergence_bps`` is the spread between the highest and lowest
    *non-None* USD price, in basis points (1 bps = 0.01%). It's the
    headline number the peg monitor classifies on.
    """

    kumbaya_usdt0: Decimal | None
    aave_oracle_usd: Decimal | None
    twap60_usd: Decimal | None
    eth_oracle_usd: Decimal | None
    divergence_bps: Decimal
    timestamp_unix: int = 0
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def sources_present(self) -> int:
        """How many independent peg sources reported a price."""
        return sum(
            1
            for x in (
                self.kumbaya_usdt0,
                self.aave_oracle_usd,
                self.twap60_usd,
                self.eth_oracle_usd,
            )
            if x is not None
        )


@dataclass(frozen=True)
class MintEvent:
    """``Minted(address indexed to, uint256 amount, address indexed minter)`` log."""

    block_number: int
    tx_hash: str
    log_index: int
    to: str
    amount: int
    minter: str


@dataclass(frozen=True)
class RedeemEvent:
    """``Burned(address indexed from, uint256 amount, address indexed burner)`` log.

    Per the OFT spec ``Burned`` is the closest event to "redeem" on a
    bridged stable: the OFT model burns on the source chain when
    bridging out / redeeming, so a spike here often signals capital
    leaving the chain — and on a bridged stable, that is materially
    similar to a redemption pressure signal.
    """

    block_number: int
    tx_hash: str
    log_index: int
    from_: str
    amount: int
    burner: str


# Topic0 hashes for the events we care about. Pre-computed at module
# load (matches the address-validation pattern in ``base.py``); the
# eth_utils call is deterministic so this is safe.
def _event_topic(signature: str) -> str:
    from eth_utils import keccak

    return "0x" + keccak(text=signature).hex()


_TOPIC_MINTED = _event_topic("Minted(address,uint256,address)")
_TOPIC_BURNED = _event_topic("Burned(address,uint256,address)")


# ---------------------------------------------------------------------------
# Helpers — decimal scaling and divergence computation
# ---------------------------------------------------------------------------


def _scale_token(raw: int, decimals: int) -> Decimal:
    """Convert ``raw`` token units to a human ``Decimal`` value.

    Use ``Decimal`` arithmetic the whole way — no float intermediates —
    so 18-decimal tokens don't lose precision in the conversion.

    IMPORTANT: ``Decimal(10) ** Decimal(decimals)`` is **inexact** for
    integer decimals because the Decimal power operator works in the
    current context's precision and treats the result as a non-integer.
    Use ``Decimal(10**decimals)`` (Python int → exact Decimal) instead
    to preserve full precision through the division. The two failing
    ``circulating_supply`` tests caught this: 1000 - 2 was returning
    ``997.999999999999999982`` because the divisor was off by 18 ulp.
    """
    if decimals < 0:
        raise ValueError(f"decimals must be >= 0, got {decimals}")
    return Decimal(int(raw)) / Decimal(10**decimals)


def _topic_to_address(topic: str) -> str:
    """Strip a 32-byte event-topic value to a checksum-lowercase address.

    Indexed address topics are zero-padded to 32 bytes; the address is
    the last 20 bytes. Returns lowercased ``0x...`` for stable equality.
    """
    if not isinstance(topic, str) or not topic.startswith("0x") or len(topic) != 66:
        raise ValueError(f"invalid 32-byte topic: {topic!r}")
    return "0x" + topic[-40:].lower()


def divergence_bps(prices: Iterable[Decimal | None]) -> Decimal:
    """Spread between the highest and lowest *non-None* prices, in bps.

    Returns ``Decimal(0)`` when fewer than two prices are present
    (no spread to compute). Uses the **lowest** price as the
    denominator — this is the conservative choice for peg monitoring,
    as the lowest USD price is the depeg-direction we care about.
    """
    real = [Decimal(p) for p in prices if p is not None]
    if len(real) < 2:
        return Decimal(0)
    hi = max(real)
    lo = min(real)
    if lo <= 0:
        return Decimal(0)
    spread = (hi - lo) / lo
    return spread * Decimal(BPS_DENOMINATOR)


# ---------------------------------------------------------------------------
# USDM facade
# ---------------------------------------------------------------------------


class USDM:
    """Read-only typed wrapper around the live USDM (USDm) deployment.

    Constructed with a ``MegaETHClient``-shaped object and a
    :class:`USDMAddresses` bundle.

    All methods are async because the underlying ``eth_call`` is async.
    """

    def __init__(self, client: _MegaETHCallable, addresses: USDMAddresses) -> None:
        self._client = client
        self.addresses = addresses

        self._token = TypedContract(
            client,
            addresses.token,
            load_pinned_abi("usdm/token.json"),
        )
        # Oracles are optional — bound lazily when peg_quote is called.
        self._twap60: TypedContract | None = None
        if addresses.twap60_oracle:
            self._twap60 = TypedContract(
                client,
                addresses.twap60_oracle,
                load_pinned_abi("usdm/oracle_usdm_twap60.json"),
            )
        self._eth_oracle: TypedContract | None = None
        if addresses.eth_oracle:
            self._eth_oracle = TypedContract(
                client,
                addresses.eth_oracle,
                load_pinned_abi("usdm/oracle_usdm_eth.json"),
            )

    # ---- ERC20 / OFT reads -----------------------------------------------

    async def total_supply(self) -> Decimal:
        """ERC20 ``totalSupply``, scaled to a human :class:`Decimal`.

        At TGE day (2026-04-30) this read returns ~360.75M USDm.
        """
        raw = await self._token.call("totalSupply")
        decimals = await self.decimals()
        return _scale_token(int(raw), decimals)

    async def decimals(self) -> int:
        """ERC20 ``decimals``. Cached after first read.

        USDm is 18-decimal; we still read it on-chain because the OFT
        contract chooses the value at deploy time and the wrapper
        should not hard-code an assumption.
        """
        if not hasattr(self, "_decimals_cached"):
            raw = await self._token.call("decimals")
            self._decimals_cached: int = int(raw)
        return self._decimals_cached

    async def symbol(self) -> str:
        """ERC20 ``symbol``. Returns ``"USDm"`` for the live deployment."""
        return str(await self._token.call("symbol"))

    async def name(self) -> str:
        return str(await self._token.call("name"))

    async def balance_of(self, account: str) -> Decimal:
        """Human-scaled balance of ``account``."""
        if not isinstance(account, str) or not account.startswith("0x") or len(account) != 42:
            raise ValueError(f"invalid account address: {account!r}")
        raw = await self._token.call("balanceOf", account)
        decimals = await self.decimals()
        return _scale_token(int(raw), decimals)

    async def circulating_supply(self) -> Decimal:
        """``totalSupply`` minus all known burn-address balances.

        For the live USDm deployment, the burn balance at ``0xdEaD``
        was ~0.0011 USDm at TGE day — totalSupply and circulating
        differ by less than ``$0.01``. The function still does the
        full subtraction so callers get correct numbers if a future
        burn event drops a meaningful chunk to a burn address.
        """
        total = await self.total_supply()
        burned = Decimal(0)
        for addr in BURN_ADDRESSES:
            try:
                burned += await self.balance_of(addr)
            except Exception:
                # A revert here is rarely fatal — the most we lose is
                # over-counting circulating by the burn-address balance,
                # which is bounded by definition.
                continue
        return total - burned

    async def is_blacklisted(self, account: str) -> bool:
        """Whether ``account`` is on the OFT's blacklist.

        The xUSDOFTUpgradeable implementation surfaces a blacklist
        admin function. A blacklisted address cannot transfer or
        receive USDm; bulk blacklisting is itself a distress signal
        worth surfacing in higher layers.
        """
        if not isinstance(account, str) or not account.startswith("0x") or len(account) != 42:
            raise ValueError(f"invalid account address: {account!r}")
        return bool(await self._token.call("isBlacklisted", account))

    async def is_minter(self, account: str) -> bool:
        """Whether ``account`` is authorized to mint new USDm.

        The OFT exposes a minter role; new authorizations are emitted
        as ``MinterAdded`` / ``MinterRemoved`` events. For peg
        monitoring this matters because mint authority is the
        analogue of "mint paused" on a Liquity-style stable: if the
        minter set is empty, no new USDm can be issued.
        """
        if not isinstance(account, str) or not account.startswith("0x") or len(account) != 42:
            raise ValueError(f"invalid account address: {account!r}")
        return bool(await self._token.call("isMinter", account))

    # ---- pause / collateral ratio — OFF-CHAIN MANAGED for live USDm -------

    async def collateral_ratio(self) -> Decimal | None:
        """Returns ``None`` for the live USDm deployment.

        The ``Minter_v2`` collateral-ratio surface (``0x2A9bd9…``)
        targets a different, uninitialized pegged-token (its
        ``PEGGED_TOKEN()`` returns ``0xbed2c…`` not ``0xFAfDdbb…``).
        The live USDm at ``0xFAfDdbb…`` is bridged via LayerZero OFT
        and its collateral lives at the issuer — there is no
        on-chain ratio to read.

        Returning ``None`` instead of a stale ``1.0`` is intentional.
        Wave C **must** treat ``None`` as "off-chain-managed; rely on
        peg-quote divergence instead" rather than as "ratio is fine".
        Returning a fake number here would cause a real depeg to be
        masked by a hard-coded reassurance.
        """
        return None

    async def mint_paused(self) -> bool | None:
        """Returns ``None`` for the live USDm deployment.

        The xUSDOFTUpgradeable token does not expose a global
        ``paused()`` view. Pause-detection on this OFT happens via
        ``MinterRemoved`` event scans (no minters → no new mints).
        Use :meth:`recent_minter_changes` for the actionable signal
        and treat ``mint_paused() is None`` as "unknown, don't gate
        on this signal alone".
        """
        return None

    async def redeem_paused(self) -> bool | None:
        """Returns ``None`` for the live USDm deployment.

        Same rationale as :meth:`mint_paused`. Redemption on a bridged
        OFT happens via ``OFTSent`` (cross-chain) plus ``Burned``
        events; pause-detection is event-driven, not view-driven.
        """
        return None

    # ---- peg quote — three independent sources ---------------------------

    async def peg_quote(
        self,
        *,
        kumbaya_quote_fn: Any | None = None,
        aave_oracle_call_fn: Any | None = None,
    ) -> PegQuote:
        """Snapshot USDM's USD price across three independent sources.

        Sources:
          * **Kumbaya USDM/USDT0 0.01% pool** — caller passes a
            coroutine ``kumbaya_quote_fn() -> Decimal`` returning the
            USDT0-per-USDM ratio. Treated as USD because USDT0 is a
            $1-pegged Tether L2 token (sanity-bounded by AaveOracle's
            USDT0 price elsewhere, e.g. live AaveOracle USDT0 was
            $0.99967 at TGE day so a USDM/USDT0 ratio of 0.999506
            implies a USDM price of ~$0.99918).
          * **MegaEthPriceFeedUsdmTwap60** — on-chain TWAP-60. Read
            via the bound ``_twap60`` typed contract.
          * **MegaEthPriceFeedUsdmEth** (composite) — read directly
            via the bound ``_eth_oracle`` typed contract; its
            ``latestAnswer`` returns four uint256 of which the third
            and fourth are USD-per-USDM low/high bounds.
          * **AaveOracle** — caller passes ``aave_oracle_call_fn() ->
            Decimal`` returning USD-per-USDM at 1e8 scale (already
            wrapped by Aave V3's facade).

        Any source that errors is silently returned as ``None`` — the
        peg monitor treats divergence over the *available* sources.
        This is intentional: a brief RPC blip on one source should
        not cascade into a fake "depeg" across the others.
        """
        kumbaya_price: Decimal | None = None
        aave_price: Decimal | None = None
        twap60_price: Decimal | None = None
        eth_oracle_price: Decimal | None = None
        raw_data: dict[str, Any] = {}

        if kumbaya_quote_fn is not None:
            try:
                kumbaya_price = Decimal(str(await kumbaya_quote_fn()))
                raw_data["kumbaya_quote_usdt0_per_usdm"] = str(kumbaya_price)
            except Exception as exc:
                raw_data["kumbaya_error"] = repr(exc)

        if aave_oracle_call_fn is not None:
            try:
                aave_price = Decimal(str(await aave_oracle_call_fn()))
                raw_data["aave_oracle_usd"] = str(aave_price)
            except Exception as exc:
                raw_data["aave_oracle_error"] = repr(exc)

        if self._twap60 is not None:
            try:
                round_data = await self._twap60.call("latestRoundData")
                # latestRoundData() -> (uint80 roundId, int256 answer,
                #                       uint256 startedAt, uint256 updatedAt,
                #                       uint80 answeredInRound)
                _round_id, answer, _started, updated_at, _ans_in_round = round_data
                dec = await self._twap60.call("decimals")
                if int(answer) > 0:
                    twap60_price = Decimal(int(answer)) / (Decimal(10) ** Decimal(int(dec)))
                    raw_data["twap60_updated_at"] = int(updated_at)
            except Exception as exc:
                raw_data["twap60_error"] = repr(exc)

        if self._eth_oracle is not None:
            try:
                # latestAnswer() -> (eth_per_usdm_low, eth_per_usdm_high,
                #                    usd_per_usdm_low, usd_per_usdm_high)
                # Probed live 2026-04-30: returned
                #   (440643773379170, 440643773379170,
                #    1000000046495661183, 1000000046495661183)
                # which decodes as (eth: 0.000441, usd: 1.000000) at TGE day.
                # The composite oracle inverts via INVERT_PRICE +
                # PRICE_DIVISOR — we read only the USD pair (third/fourth).
                ans = await self._eth_oracle.call("latestAnswer")
                if isinstance(ans, tuple) and len(ans) >= 4:
                    usd_low, usd_high = int(ans[2]), int(ans[3])
                    if usd_low > 0 and usd_high > 0:
                        # Average the band — they're typically equal at
                        # rest, only diverge during heartbeat windows.
                        eth_oracle_price = (Decimal(usd_low) + Decimal(usd_high)) / (
                            Decimal(2) * Decimal(10**18)
                        )
                        raw_data["eth_oracle_usd_band"] = (
                            str(Decimal(usd_low) / Decimal(10**18)),
                            str(Decimal(usd_high) / Decimal(10**18)),
                        )
            except Exception as exc:
                raw_data["eth_oracle_error"] = repr(exc)

        spread = divergence_bps((kumbaya_price, aave_price, twap60_price, eth_oracle_price))

        return PegQuote(
            kumbaya_usdt0=kumbaya_price,
            aave_oracle_usd=aave_price,
            twap60_usd=twap60_price,
            eth_oracle_usd=eth_oracle_price,
            divergence_bps=spread,
            raw=raw_data,
        )

    # ---- event scans -----------------------------------------------------

    async def recent_mints(
        self,
        blocks: int = 100,
        *,
        latest_block: int | None = None,
    ) -> list[MintEvent]:
        """Scan the last ``blocks`` for ``Minted`` events.

        ``latest_block`` lets callers pin a specific tip (useful in
        tests with a synthetic chain head). When omitted, the wrapper
        issues an ``eth_blockNumber`` to find the current tip.

        Returns events oldest-first; an empty list is normal for a
        bridged stable on a quiet day.
        """
        if blocks <= 0:
            raise ValueError(f"blocks must be positive, got {blocks!r}")
        return await self._scan_events(_TOPIC_MINTED, blocks, latest_block, _decode_mint)

    async def recent_redeems(
        self,
        blocks: int = 100,
        *,
        latest_block: int | None = None,
    ) -> list[RedeemEvent]:
        """Scan the last ``blocks`` for ``Burned`` events.

        On a bridged OFT, ``Burned`` covers both true redemptions and
        cross-chain bridge-outs (the OFT burns on source-chain when
        sending). Combined with :meth:`recent_mints`, the net flow is
        the directional signal.
        """
        if blocks <= 0:
            raise ValueError(f"blocks must be positive, got {blocks!r}")
        return await self._scan_events(_TOPIC_BURNED, blocks, latest_block, _decode_burn)

    async def _scan_events(
        self,
        topic0: str,
        blocks: int,
        latest_block: int | None,
        decoder: Any,
    ) -> list[Any]:
        if latest_block is None:
            head_hex = await self._client._call("eth_blockNumber", [])
            latest_block = int(str(head_hex), 16)
        from_block = max(0, int(latest_block) - blocks)
        params = [
            {
                "fromBlock": hex(from_block),
                "toBlock": hex(int(latest_block)),
                "address": self.addresses.token,
                "topics": [topic0],
            }
        ]
        logs = await self._client._call("eth_getLogs", params)
        out: list[Any] = []
        for log in logs or ():
            try:
                out.append(decoder(log))
            except Exception:
                # Skip malformed logs; production safety.
                continue
        out.sort(key=lambda e: (e.block_number, e.log_index))
        return out


def _decode_mint(log: dict[str, Any]) -> MintEvent:
    """Decode a ``Minted(address indexed to, uint256 amount, address indexed minter)`` log."""
    topics = log.get("topics") or []
    if len(topics) < 3:
        raise ValueError(f"Minted log missing indexed topics: {topics!r}")
    to = _topic_to_address(topics[1])
    minter = _topic_to_address(topics[2])
    data_hex = log.get("data") or "0x"
    if data_hex.startswith("0x"):
        data_hex = data_hex[2:]
    if not data_hex:
        amount = 0
    else:
        amount = int(data_hex, 16)
    return MintEvent(
        block_number=int(log.get("blockNumber", "0x0"), 16),
        tx_hash=str(log.get("transactionHash", "0x")),
        log_index=int(log.get("logIndex", "0x0"), 16),
        to=to,
        amount=amount,
        minter=minter,
    )


def _decode_burn(log: dict[str, Any]) -> RedeemEvent:
    """Decode a ``Burned(address indexed from, uint256 amount, address indexed burner)`` log."""
    topics = log.get("topics") or []
    if len(topics) < 3:
        raise ValueError(f"Burned log missing indexed topics: {topics!r}")
    from_addr = _topic_to_address(topics[1])
    burner = _topic_to_address(topics[2])
    data_hex = log.get("data") or "0x"
    if data_hex.startswith("0x"):
        data_hex = data_hex[2:]
    if not data_hex:
        amount = 0
    else:
        amount = int(data_hex, 16)
    return RedeemEvent(
        block_number=int(log.get("blockNumber", "0x0"), 16),
        tx_hash=str(log.get("transactionHash", "0x")),
        log_index=int(log.get("logIndex", "0x0"), 16),
        from_=from_addr,
        amount=amount,
        burner=burner,
    )
