"""Off-chain Pyth Hermes price-feed client.

Pyth publishes prices off-chain on a sub-second cadence and *also*
caches them on-chain — but the on-chain cache only updates when
someone calls ``updatePriceFeeds`` (a gas-paid keeper action). On a
chain with sparse keepers, the cached price can lag arbitrarily — at
the time of writing PR #621 documents an Optimism BTC cache that is
**25 days stale**, producing a 1066 bps "divergence" against
Arbitrum's fresher cache that is purely an artifact of stale on-chain
data, not a real off-chain price gap.

Hermes (https://hermes.pyth.network) is Pyth's public off-chain
price-feed API. It returns the same VAA-encoded price update that
keepers submit to the on-chain ``updatePriceFeeds`` call, plus a
parsed JSON view (``price``, ``conf``, ``expo``, ``publish_time``).
The publish_time on Hermes is sub-second-fresh by definition — it's
the source the keepers themselves read from.

This module is the **chain-agnostic complement** to the per-chain
on-chain Pyth wrappers under :mod:`lib.chains.<chain>.contracts.
pyth_oracle`. The on-chain wrappers remain useful for flows that
genuinely need the cached on-chain value (e.g. paying gas to refresh
it via ``updatePriceFeeds`` so a downstream contract reads the new
price atomically). For pure *price observation* — the dominant case
on the dashboard, in signal generators, and in stale-cache detection
— Hermes is the ground truth that bypasses on-chain keeper cadence.

Why this is a distinct module
=============================

Single-chain pricing pipelines that route through the on-chain Pyth
wrapper inherit that chain's keeper cadence. When Sapphire's chain-
health gate or divergence detector reads on-chain Pyth on three
chains and they disagree, **the comparison is comparing three
different stale snapshots of the same off-chain feed**, not three
independent price observations. This is exactly the
"stale-cache reporter" failure mode PR #621 surfaced.

Hermes provides the missing reference: one fresh, off-chain reading
the operator can pin against to distinguish

* **stale-cache divergence** — on-chain values disagree with each
  other, but Hermes is in the middle (the gap is a keeper-lag
  artifact, not a real price gap)
* **real divergence** — Hermes is offset from *all* on-chain reads
  in the same direction (a true off-chain price move that the
  on-chain caches haven't seen yet — actionable, but the trade is
  "wait for the keepers to refresh", not "arb between chains")

The downstream divergence scanner under
:mod:`lib.chains.cross_chain.pyth_divergence` can opt into Hermes
via ``include_hermes=True`` to surface this distinction.

Usage
-----

>>> client = PythHermesClient()
>>> px = client.latest_price(b"\\xe6...\\x43")  # BTC priceId
>>> px.usd  # Decimal
Decimal('78671.62')

>>> prices = client.latest_prices_by_symbol(["BTC", "ETH", "SOL"])
>>> prices["BTC"].publish_time
1777818495

The client is sync (Hermes responses are small JSON payloads, no
need for async overhead in the critical path) and uses ``httpx``.
Caller decides freshness threshold — Hermes responses are always
fresh (sub-second) under normal operation, so no staleness flag is
exposed at this layer. The divergence detector classifies stale-vs-
real based on the cross-chain comparison, not on the Hermes age.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: Default Hermes base URL. Public, no auth required. The path
#: ``/v2/updates/price/latest`` is the documented "fetch latest update"
#: endpoint that returns both the VAA-encoded ``binary.data`` (for
#: anyone who wants to feed it into ``updatePriceFeeds`` to refresh
#: the on-chain cache) and a ``parsed`` JSON view.
DEFAULT_HERMES_BASE_URL = "https://hermes.pyth.network"

#: Canonical symbol → priceId map. These are the *Pyth* priceIds —
#: they are chain-agnostic (a priceId identifies a feed, not a
#: deployment), so the same hex strings work for MegaETH, Arbitrum,
#: Optimism, and Hermes alike. Mirrored from the per-chain wrappers
#: (``MEGAETH_PRICE_IDS`` / ``ARBITRUM_PRICE_IDS`` /
#: ``OPTIMISM_PRICE_IDS``) — they all agree because Pyth assigns one
#: priceId per underlying asset globally.
HERMES_PRICE_IDS: dict[str, str] = {
    "BTC": "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "ETH": "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "SOL": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "USDC": "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "USDT": "0x2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b",
}


def _normalize_price_id(price_id: str | bytes) -> bytes:
    """Coerce a hex string or bytes priceId to canonical 32-byte form.

    Mirrors the validation in the per-chain Pyth wrappers so the same
    inputs work everywhere. Accepts ``"0x..."``, ``"..."`` (no
    prefix), or raw bytes. Raises ``ValueError`` on length mismatch
    so a typo fails fast at construction time rather than silently
    returning the wrong feed.
    """
    if isinstance(price_id, bytes):
        raw = price_id
    elif isinstance(price_id, str):
        s = price_id.strip()
        if s.startswith(("0x", "0X")):
            s = s[2:]
        if len(s) != 64:
            raise ValueError(
                "invalid Pyth priceId hex length: expected 64 hex chars, "
                f"got {len(s)} (input={price_id!r})"
            )
        try:
            raw = bytes.fromhex(s)
        except ValueError as exc:
            raise ValueError(f"invalid Pyth priceId hex: {price_id!r}") from exc
    else:
        raise TypeError(
            f"priceId must be str or bytes, got {type(price_id).__name__}"
        )
    if len(raw) != 32:
        raise ValueError(f"Pyth priceId must be 32 bytes, got {len(raw)}")
    return raw


def _price_id_hex(price_id: str | bytes) -> str:
    """Return a 0x-prefixed lowercase hex string for ``price_id``.

    Hermes accepts both with and without the ``0x`` prefix on the
    query side, but we always send the prefixed form for symmetry
    with how priceIds are stored in the per-chain wrappers.
    """
    return "0x" + _normalize_price_id(price_id).hex()


def _price_id_key(price_id: str | bytes) -> bytes:
    """Canonical bytes key used in ``latest_prices`` return dicts.

    Hermes responses key by un-prefixed lowercase hex; we round-trip
    through ``_normalize_price_id`` so callers can pass either form
    and we always return the same 32-byte key.
    """
    return _normalize_price_id(price_id)


@dataclass(frozen=True)
class PythHermesPrice:
    """One off-chain Pyth Hermes price observation.

    The numeric fields mirror the on-chain ``PriceFeed`` struct
    layout (``int64 price * 10**expo``, ``uint64 conf``,
    ``uint64 publish_time``). The ``vaa_bytes`` field carries the
    VAA-encoded update payload — anyone who wants to refresh an
    on-chain cache via ``IPyth.updatePriceFeeds(bytes[])`` can pass
    this directly. We expose the raw bytes rather than the hex string
    because that's the form ``updatePriceFeeds`` expects.

    Per-feed precision is preserved as :class:`decimal.Decimal` —
    Pyth's ``int64 * 10**expo`` is exact in Decimal but lossy in
    float, and we want bit-exact equality with the on-chain wrappers.
    """

    price: Decimal
    """USD price as ``int64 price * Decimal(10) ** expo``."""

    conf: Decimal
    """Confidence interval (one standard deviation) in the same
    units as ``price``."""

    expo: int
    """Exponent applied to the raw int64 price. Always negative for
    USD feeds (e.g. ``-8`` means the int64 is in 10^-8 USD)."""

    publish_time: int
    """Unix seconds — when the Pythnet aggregator published this
    price. Hermes returns this verbatim; on-chain caches store the
    same value once a keeper submits the update."""

    vaa_bytes: bytes
    """VAA-encoded price update payload. Pass this to
    ``IPyth.updatePriceFeeds([vaa_bytes])`` to refresh an on-chain
    cache. Empty bytes when binary data was not requested."""

    @property
    def usd(self) -> Decimal:
        """Alias for :attr:`price`. Mirrors the per-chain wrappers'
        ``PythRegistryPrice.usd`` attribute so code that accepts
        either type can read ``.usd`` uniformly."""
        return self.price

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (Decimals → strings,
        bytes → hex)."""
        return {
            "price": str(self.price),
            "conf": str(self.conf),
            "expo": int(self.expo),
            "publish_time": int(self.publish_time),
            "vaa_hex": self.vaa_bytes.hex() if self.vaa_bytes else "",
        }


class PythHermesClient:
    """Sync client for the public Hermes off-chain price feed.

    Hermes responses are small JSON (a few KB even for batch fetches
    of all 5 majors) so async-everywhere is overkill — this client
    stays sync to keep the call site readable and testable. Callers
    that need concurrency can wrap with ``asyncio.to_thread`` or
    parallelize at a higher layer.

    The client holds a ``httpx.Client`` for connection reuse across
    calls. Construct once, share across the process. Thread-safe in
    the same sense ``httpx.Client`` is (one transport pool, safe to
    share). Closing is optional — ``httpx.Client`` is GC-safe — but
    callers may use this as a context manager for explicit cleanup.
    """

    #: Endpoint path for "latest price update" — the v2 batch endpoint.
    LATEST_PATH = "/v2/updates/price/latest"

    def __init__(
        self,
        base_url: str = DEFAULT_HERMES_BASE_URL,
        timeout_s: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        """Construct a Hermes client.

        Args:
            base_url: Hermes API root. Defaults to the public endpoint;
                override for testing against a private mirror.
            timeout_s: Per-request timeout. Hermes typically responds
                in <100ms so 5s is generous; tests can shorten it.
            client: Optional pre-configured ``httpx.Client``. When
                provided, the client is *not* closed on
                ``__exit__`` — caller-owned. When ``None``, we
                construct our own and close it on context exit.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=timeout_s,
                # Hermes returns large hex strings — give the response
                # parser headroom rather than streaming.
                limits=httpx.Limits(max_keepalive_connections=4),
            )
            self._owns_client = True

    def __enter__(self) -> PythHermesClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying httpx client (no-op if caller-owned)."""
        if self._owns_client:
            self._client.close()

    # -- public API --------------------------------------------------------

    def latest_price(
        self,
        price_id: str | bytes,
        *,
        include_vaa: bool = True,
    ) -> PythHermesPrice:
        """Fetch the latest off-chain price for a single priceId.

        Args:
            price_id: Hex string (with or without ``0x``) or 32 raw
                bytes — same accepted shapes as the on-chain wrappers.
            include_vaa: When True (default), the VAA-encoded update
                payload is included on the returned price. Set False
                to skip it on hot paths where you only need the
                parsed price (saves a few KB per call).

        Returns:
            One :class:`PythHermesPrice`. Hermes always returns the
            most recent price; freshness is implicit.

        Raises:
            ValueError: If the priceId is malformed.
            httpx.HTTPError: On network or HTTP-level failures.
            LookupError: If Hermes did not return a parsed entry for
                the requested priceId (typically means the feed is
                unrecognized — a typo in the priceId, since Hermes
                covers every Pyth-listed asset).
        """
        results = self.latest_prices([price_id], include_vaa=include_vaa)
        # Round-trip through the same key normalizer the batch path
        # uses so a caller passing the unprefixed hex string still
        # finds their entry.
        key = _price_id_key(price_id)
        try:
            return results[key]
        except KeyError as exc:
            raise LookupError(
                f"Hermes returned no parsed entry for priceId "
                f"{_price_id_hex(price_id)!r}"
            ) from exc

    def latest_prices(
        self,
        price_ids: list[str | bytes],
        *,
        include_vaa: bool = True,
    ) -> dict[bytes, PythHermesPrice]:
        """Batch-fetch the latest off-chain price for several priceIds.

        Args:
            price_ids: List of hex strings or 32-byte raw IDs. Mixed
                forms accepted; deduplicated server-side.
            include_vaa: When True (default), each entry carries the
                VAA-encoded update payload. Note that Hermes returns
                a single combined VAA covering all requested feeds —
                we attach the full payload to *every* returned entry
                (the on-chain ``updatePriceFeeds`` call accepts a
                single combined payload that updates many feeds at
                once, so duplicating it is a load_bearing convenience
                for callers that want to refresh just one of N feeds
                they fetched).

        Returns:
            ``{priceId_bytes: PythHermesPrice}``. Keys are the
            normalized 32-byte form so caller-supplied hex strings
            and raw bytes round-trip to the same key.

        Raises:
            ValueError: If any priceId is malformed.
            httpx.HTTPError: On network or HTTP-level failures.
        """
        if not price_ids:
            return {}

        # Normalize + dedupe while preserving order so a curious
        # caller can debug "I asked for X, why did I get Y back?"
        seen: set[bytes] = set()
        ordered: list[bytes] = []
        for raw_id in price_ids:
            key = _price_id_key(raw_id)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(key)

        # Hermes accepts repeated ``ids[]=...`` query params. We send
        # the 0x-prefixed form for symmetry with how priceIds appear
        # in the per-chain wrapper registries. ``parsed=true`` is the
        # default but pin it explicitly — defensive against future
        # API drift.
        params: list[tuple[str, str]] = [
            ("ids[]", "0x" + key.hex()) for key in ordered
        ]
        params.append(("parsed", "true"))
        if not include_vaa:
            params.append(("encoding", "hex"))
            # Note: Hermes always returns ``binary.data`` even when
            # the caller doesn't want it. ``include_vaa=False`` is
            # honored by *not parsing it* into the result, not by
            # asking Hermes to omit it. This keeps the wire shape
            # stable across all calls.

        try:
            resp = self._client.get(self.LATEST_PATH, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Hermes fetch failed: %s", exc)
            raise

        body = resp.json()
        return self._parse_response(body, ordered, include_vaa=include_vaa)

    def latest_prices_by_symbol(
        self,
        symbols: list[str],
        *,
        include_vaa: bool = True,
    ) -> dict[str, PythHermesPrice]:
        """Batch-fetch by canonical symbol (BTC / ETH / SOL / ...).

        Convenience wrapper over :meth:`latest_prices` that uses the
        :data:`HERMES_PRICE_IDS` map. Unknown symbols raise — fail
        fast rather than silently dropping.

        Args:
            symbols: List of canonical symbols (case-insensitive).
            include_vaa: See :meth:`latest_prices`.

        Returns:
            ``{symbol_uppercase: PythHermesPrice}``.

        Raises:
            KeyError: If any symbol is not in :data:`HERMES_PRICE_IDS`.
        """
        normalized = [s.strip().upper() for s in symbols]
        unknown = [s for s in normalized if s not in HERMES_PRICE_IDS]
        if unknown:
            raise KeyError(
                f"unknown Hermes symbol(s): {unknown}. Known: "
                f"{sorted(HERMES_PRICE_IDS)}"
            )

        # Build the priceId list in the same order as ``normalized``
        # so the result iteration order is stable for callers that
        # care.
        ids = [HERMES_PRICE_IDS[s] for s in normalized]
        by_id = self.latest_prices(ids, include_vaa=include_vaa)

        out: dict[str, PythHermesPrice] = {}
        for sym, hex_id in zip(normalized, ids, strict=True):
            key = _price_id_key(hex_id)
            if key in by_id:
                out[sym] = by_id[key]
        return out

    # -- internals ---------------------------------------------------------

    def _parse_response(
        self,
        body: dict[str, Any],
        requested: list[bytes],
        *,
        include_vaa: bool,
    ) -> dict[bytes, PythHermesPrice]:
        """Convert a Hermes JSON body into ``{priceId: PythHermesPrice}``.

        The response shape (verified against the live API on
        2026-05-02) is::

            {
              "binary": {
                "encoding": "hex",
                "data": ["<combined VAA hex>"]
              },
              "parsed": [
                {
                  "id": "<priceId hex, no 0x prefix>",
                  "price": {"price": "<int>", "conf": "<int>",
                            "expo": <int>, "publish_time": <int>},
                  "ema_price": {...},
                  "metadata": {...}
                },
                ...
              ]
            }

        We ignore ``ema_price`` and ``metadata`` — they're not part
        of the canonical price observation a divergence detector
        compares against the on-chain cache. Future iterations could
        surface the EMA on a richer dataclass.
        """
        parsed = body.get("parsed") or []
        if not isinstance(parsed, list):
            raise ValueError(
                f"Hermes response missing 'parsed' list (got {type(parsed).__name__})"
            )

        # Combined VAA payload — Hermes returns a single hex string
        # in ``binary.data[0]`` covering every requested feed. The
        # on-chain ``updatePriceFeeds(bytes[])`` accepts an array, so
        # we wrap into a single-element list at call time.
        vaa_bytes = b""
        if include_vaa:
            binary = body.get("binary") or {}
            data = binary.get("data") or []
            encoding = binary.get("encoding", "hex")
            if data and encoding == "hex":
                # First entry is the canonical update; ignore any
                # additional entries (Hermes occasionally returns
                # multiple in edge cases — the combined first entry
                # is the one updatePriceFeeds expects).
                try:
                    vaa_bytes = bytes.fromhex(data[0])
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Hermes binary.data[0] not valid hex: %s", exc
                    )
                    vaa_bytes = b""

        out: dict[bytes, PythHermesPrice] = {}
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            id_hex = entry.get("id", "")
            try:
                key = _price_id_key(id_hex)
            except (ValueError, TypeError):
                logger.warning("Hermes returned invalid priceId %r", id_hex)
                continue

            price_obj = entry.get("price") or {}
            try:
                raw_price = int(price_obj["price"])
                raw_conf = int(price_obj["conf"])
                expo = int(price_obj["expo"])
                publish_time = int(price_obj["publish_time"])
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Hermes parsed entry %s missing fields: %s", id_hex, exc
                )
                continue

            # Decimal math: int64 * 10**expo. expo is typically
            # negative (e.g. -8), so 10**expo is a fractional Decimal.
            scale = Decimal(10) ** expo
            price = Decimal(raw_price) * scale
            conf = Decimal(raw_conf) * scale

            out[key] = PythHermesPrice(
                price=price,
                conf=conf,
                expo=expo,
                publish_time=publish_time,
                vaa_bytes=vaa_bytes,
            )

        # Log unmatched requests at debug — useful when chasing why a
        # symbol disappeared from the result set, but not a hard
        # error (Hermes can omit a feed if it's freshly unlisted).
        missing = [k for k in requested if k not in out]
        if missing:
            logger.debug(
                "Hermes did not return %d requested priceId(s): %s",
                len(missing),
                [k.hex() for k in missing],
            )
        return out


__all__ = (
    "DEFAULT_HERMES_BASE_URL",
    "HERMES_PRICE_IDS",
    "PythHermesClient",
    "PythHermesPrice",
)
