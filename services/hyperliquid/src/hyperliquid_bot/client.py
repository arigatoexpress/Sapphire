"""Hyperliquid API client.

Hyperliquid is a decentralized L1 perpetuals exchange.
Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api

API Endpoints:
  REST:     https://api.hyperliquid.xyz
  Testnet:  https://api.hyperliquid-testnet.xyz
  WS:       wss://api.hyperliquid.xyz/ws

Authentication: EIP-712 signed actions (uses eth_account / local key signing).
No API key required — wallet private key signs all order actions. See
``signing.py`` for the L1 action signing scheme (msgpack action || nonce ||
vault || expiry → keccak256 → phantom Agent → typed-data sign).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import eth_account
import httpx
from eth_account.signers.local import LocalAccount

from .signing import float_to_wire, sign_l1_action

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
TESTNET_URL = "https://api.hyperliquid-testnet.xyz"


class HyperliquidClient:
    """Async Hyperliquid REST + WebSocket client.

    Args:
        private_key: Hex wallet private key (0x-prefixed).
        testnet: Use testnet if True.
    """

    def __init__(self, private_key: str, *, testnet: bool = False) -> None:
        self._account: LocalAccount = eth_account.Account.from_key(private_key)
        self.address = self._account.address
        self.testnet = testnet
        self.base_url = TESTNET_URL if testnet else BASE_URL
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HyperliquidClient:
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=15.0)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._http:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Public / Market data (no auth)
    # ------------------------------------------------------------------

    async def get_meta(self) -> dict[str, Any]:
        """Get exchange metadata — asset list, leverage tiers, fees."""
        resp = await self._post_info({"type": "meta"})
        return resp

    async def get_all_mids(self) -> dict[str, str]:
        """Get mid prices for all assets. Returns {symbol: price_str}."""
        resp = await self._post_info({"type": "allMids"})
        return resp

    async def get_orderbook(self, coin: str) -> dict[str, Any]:
        """Get L2 order book for a coin (e.g. 'BTC')."""
        return await self._post_info({"type": "l2Book", "coin": coin})

    async def get_user_state(self) -> dict[str, Any]:
        """Get account state: margin summary, positions, open orders."""
        return await self._post_info({"type": "clearinghouseState", "user": self.address})

    async def get_open_orders(self) -> list[dict[str, Any]]:
        """Get all open orders for this account."""
        resp = await self._post_info({"type": "openOrders", "user": self.address})
        return resp if isinstance(resp, list) else []

    # ------------------------------------------------------------------
    # Order execution (requires signing)
    # ------------------------------------------------------------------

    async def market_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        *,
        reduce_only: bool = False,
        slippage: float = 0.001,
    ) -> dict[str, Any]:
        """Place a market order with slippage-protected limit price.

        Hyperliquid has no true market order — we use an aggressive limit.
        slippage of 0.1% (0.001) means 0.1% above/below mid for buy/sell.
        """
        mids = await self.get_all_mids()
        mid = float(mids.get(coin, 0))
        if not mid:
            raise ValueError(f"No mid price for {coin}")

        limit_px = mid * (1 + slippage) if is_buy else mid * (1 - slippage)
        return await self.limit_order(
            coin, is_buy, sz, limit_px, tif="Ioc", reduce_only=reduce_only
        )

    async def limit_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        *,
        tif: str = "Gtc",
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Place a limit order.

        Args:
            coin: Asset symbol (e.g. 'BTC', 'ETH', 'SOL').
            is_buy: True for long/buy, False for short/sell.
            sz: Size in base asset.
            limit_px: Limit price in USD.
            tif: Time-in-force: 'Gtc' | 'Ioc' | 'Alo'.
            reduce_only: Only reduce an existing position.
        """
        action = {
            "type": "order",
            "orders": [
                {
                    "a": await self._asset_index(coin),
                    "b": is_buy,
                    "p": self._px_str(limit_px),
                    "s": self._sz_str(sz),
                    "r": reduce_only,
                    "t": {"limit": {"tif": tif}},
                }
            ],
            "grouping": "na",
        }
        return await self._exchange_action(action)

    async def cancel_order(self, coin: str, order_id: int) -> dict[str, Any]:
        """Cancel an open order by ID."""
        action = {
            "type": "cancel",
            "cancels": [{"a": await self._asset_index(coin), "o": order_id}],
        }
        return await self._exchange_action(action)

    async def close_position(self, coin: str) -> dict[str, Any]:
        """Market-close an open position."""
        state = await self.get_user_state()
        for pos in state.get("assetPositions", []):
            p = pos.get("position", {})
            if p.get("coin") == coin:
                szi = float(p.get("szi", 0))
                if szi == 0:
                    return {"status": "no_position"}
                is_buy = szi < 0  # close short = buy
                return await self.market_order(coin, is_buy, abs(szi), reduce_only=True)
        return {"status": "no_position"}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _post_info(self, body: dict[str, Any]) -> Any:
        assert self._http, "Use as async context manager"
        r = await self._http.post("/info", json=body)
        r.raise_for_status()
        return r.json()

    async def _exchange_action(
        self,
        action: dict[str, Any],
        *,
        vault_address: str | None = None,
        expires_after: int | None = None,
    ) -> dict[str, Any]:
        assert self._http, "Use as async context manager"
        nonce = int(time.time() * 1000)
        signature = sign_l1_action(
            self._account,
            action,
            vault_address=vault_address,
            nonce=nonce,
            expires_after=expires_after,
            is_mainnet=not self.testnet,
        )
        body: dict[str, Any] = {"action": action, "nonce": nonce, "signature": signature}
        if vault_address is not None:
            body["vaultAddress"] = vault_address
        if expires_after is not None:
            body["expiresAfter"] = expires_after
        r = await self._http.post("/exchange", json=body)
        r.raise_for_status()
        return r.json()

    async def _asset_index(self, coin: str) -> int:
        """Return the numeric asset index for a coin symbol."""
        meta = await self.get_meta()
        for i, asset in enumerate(meta.get("universe", [])):
            if asset.get("name", "").upper() == coin.upper():
                return i
        raise ValueError(f"Asset not found: {coin}")

    @staticmethod
    def _px_str(price: float) -> str:
        return float_to_wire(price)

    @staticmethod
    def _sz_str(size: float) -> str:
        return float_to_wire(size)
